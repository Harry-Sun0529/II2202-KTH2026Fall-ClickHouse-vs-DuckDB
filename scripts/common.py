"""Shared helpers for the driver (runs inside the privileged driver container).

- config loading
- starting / restarting the two engine containers with identical limits
- clients for ClickHouse (HTTP) and DuckDB (JSON over TCP to duck_server.py)
- cgroup memory sampler
- result normalisation and checksum (identical for both engines)
"""
from __future__ import annotations

import datetime as dt
import decimal
import glob
import hashlib
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
HOST_REPO = os.environ.get("HOST_REPO", str(ROOT))  # repo path as Docker's daemon sees it
GIB = 1024 ** 3

CH = CFG["engines"]["clickhouse"]
DK = CFG["engines"]["duckdb"]
LIM = CFG["container_limits"]
NET = CFG["docker"]["network"]
VOL = CFG["docker"]["volumes"]
QUERIES = CFG["queries"]
QCLASS = {q["id"]: q["class"] for q in QUERIES}
TABLES = CFG["data"]["tables"]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


# --------------------------------------------------------------------------- docker
def docker_client():
    import docker  # only available in the driver image
    return docker.from_env(timeout=600)


def ensure_infra(dc) -> None:
    if not dc.networks.list(names=[NET]):
        dc.networks.create(NET, driver="bridge")
    names = {v.name for v in dc.volumes.list()}
    for v in VOL.values():
        if v not in names:
            dc.volumes.create(v)


def _limits() -> dict:
    return dict(
        mem_limit=LIM["memory"],
        memswap_limit=LIM["memory_swap"],
        nano_cpus=int(LIM["cpus"] * 1e9),
        cpuset_cpus=LIM["cpuset_cpus"],
    )


def remove_container(dc, name: str) -> None:
    try:
        c = dc.containers.get(name)
        c.remove(force=True)
    except Exception:
        pass


def start_clickhouse(dc):
    import docker.types
    remove_container(dc, CH["container"])
    mounts = [
        docker.types.Mount("/var/lib/clickhouse", VOL["clickhouse"], type="volume"),
        docker.types.Mount("/var/lib/clickhouse/user_files/tpch", VOL["parquet"], type="volume", read_only=True),
        docker.types.Mount("/etc/clickhouse-server/config.d/ii2202.xml",
                           f"{HOST_REPO}/docker/clickhouse/config.d/ii2202.xml", type="bind", read_only=True),
        docker.types.Mount("/etc/clickhouse-server/users.d/ii2202.xml",
                           f"{HOST_REPO}/docker/clickhouse/users.d/ii2202.xml", type="bind", read_only=True),
    ]
    c = dc.containers.run(
        CH["image"], name=CH["container"], detach=True, network=NET, mounts=mounts,
        ulimits=[docker.types.Ulimit(name="nofile", soft=262144, hard=262144)],
        environment={"CLICKHOUSE_SKIP_USER_SETUP": "1", "CLICKHOUSE_DO_NOT_CHOWN": "1"}, **_limits(),
    )
    wait_clickhouse()
    return c


def start_duckdb(dc):
    import docker.types
    remove_container(dc, DK["container"])
    mounts = [
        docker.types.Mount("/db", VOL["duckdb"], type="volume"),
        docker.types.Mount("/data", VOL["parquet"], type="volume", read_only=True),
        docker.types.Mount("/work", HOST_REPO, type="bind", read_only=True),
    ]
    c = dc.containers.run(
        DK["image"], command=["python", "-u", "/work/scripts/duck_server.py"],
        name=DK["container"], detach=True, network=NET, mounts=mounts, **_limits(),
    )
    wait_duckdb()
    return c


def restart_engine(dc, engine: str, drop_cache: bool = True):
    """Stop the engine, drop the VM page cache, start it again (cold state)."""
    c = dc.containers.get(CH["container"] if engine == "clickhouse" else DK["container"])
    c.stop(timeout=30)
    if drop_cache:
        drop_page_cache()
    c.start()
    (wait_clickhouse if engine == "clickhouse" else wait_duckdb)()
    c.reload()
    return c


def container_state(dc, engine: str) -> dict:
    c = dc.containers.get(CH["container"] if engine == "clickhouse" else DK["container"])
    c.reload()
    return c.attrs["State"]


def drop_page_cache() -> None:
    os.sync()
    with open("/proc/sys/vm/drop_caches", "w") as f:
        f.write("3")


# --------------------------------------------------------------------------- clickhouse
class ClickHouseError(RuntimeError):
    pass


def ch_http(sql: str, *, query_id: str | None = None, settings: dict | None = None,
            timeout: float = 3600, fmt: str = "JSONCompact") -> tuple[dict | str, float]:
    """Run one statement over HTTP. Returns (parsed body, client wall time in ms)."""
    params = {"default_format": fmt}
    if query_id:
        params["query_id"] = query_id
    params.update({k: str(v) for k, v in (settings or {}).items()})
    url = f"http://{CH['container']}:8123/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=sql.encode(), method="POST")
    t0 = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        raise ClickHouseError(e.read().decode(errors="replace").strip()[:500]) from None
    ms = (time.perf_counter_ns() - t0) / 1e6
    text = body.decode()
    if fmt.startswith("JSON") and text.strip():
        return json.loads(text), ms
    return text, ms


def wait_clickhouse(timeout: float = 120) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if ch_http("SELECT 1", fmt="TSV", timeout=5)[0].strip() == "1":
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError("ClickHouse did not become ready")


# --------------------------------------------------------------------------- duckdb
class DuckError(RuntimeError):
    pass


def duck_call(req: dict, timeout: float = 3600) -> dict:
    with socket.create_connection((DK["container"], 9999), timeout=timeout) as s:
        s.sendall((json.dumps(req) + "\n").encode())
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                raise DuckError("connection closed by duck_server")
            buf += chunk
    resp = json.loads(buf)
    if resp.get("error"):
        raise DuckError(resp["error"])
    return resp


def wait_duckdb(timeout: float = 120) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if duck_call({"op": "ping"}, timeout=5).get("ok"):
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError("duck_server did not become ready")


# --------------------------------------------------------------------------- memory
def cgroup_dir(container_id: str) -> str:
    hits = glob.glob(f"/sys/fs/cgroup/docker/{container_id}") or \
        glob.glob(f"/sys/fs/cgroup/**/*{container_id}*", recursive=True)
    if not hits:
        raise FileNotFoundError(f"cgroup of {container_id} not found")
    return hits[0]


def read_int(path: str) -> int:
    with open(path) as f:
        return int(f.read())


def read_anon(stat_path: str) -> int:
    with open(stat_path) as f:
        for line in f:
            if line.startswith("anon "):
                return int(line.split()[1])
    return 0


class CgroupSampler:
    """Samples memory.current and memory.stat:anon of one container's cgroup.

    Also resets the kernel's memory.peak watermark at start (Linux >= 6.12 keeps
    a per-file-descriptor watermark after a write) and reads it at stop, so the
    sampled maximum can be checked against the exact kernel watermark.
    """

    def __init__(self, container_id: str, interval_ms: float):
        self.dir = cgroup_dir(container_id)
        self.interval = interval_ms / 1000
        self._stop = threading.Event()
        self.max_current = 0
        self.max_anon = 0
        self.n = 0

    def baseline(self) -> int:
        return read_int(f"{self.dir}/memory.current")

    def _loop(self):
        cur_p, stat_p = f"{self.dir}/memory.current", f"{self.dir}/memory.stat"
        while not self._stop.is_set():
            try:
                cur = read_int(cur_p)
                anon = read_anon(stat_p)
            except (OSError, ValueError):
                break  # cgroup vanished (container died)
            self.max_current = max(self.max_current, cur)
            self.max_anon = max(self.max_anon, anon)
            self.n += 1
            time.sleep(self.interval)

    def __enter__(self):
        self._peak_fd = open(f"{self.dir}/memory.peak", "r+")
        self._peak_fd.write("reset\n")
        self._peak_fd.flush()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        try:
            self._peak_fd.seek(0)
            self.watermark = int(self._peak_fd.read())
        except (OSError, ValueError):
            self.watermark = None
        finally:
            try:
                self._peak_fd.close()
            except OSError:
                pass
        return False


# --------------------------------------------------------------------------- results
def _norm(v) -> str:
    """Canonical text for one value: numbers rounded to 2 decimals, dates ISO."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (float, decimal.Decimal)):
        d = decimal.Decimal(str(v)).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_EVEN)
        return "0.00" if d == 0 else str(d)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return str(v).rstrip()


def typed_value(v, type_name: str):
    """Turn a ClickHouse/DuckDB JSON value back into a Python value by its SQL type."""
    t = type_name.upper().replace(" ", "")
    for wrapper in ("NULLABLE(", "LOWCARDINALITY("):
        while t.startswith(wrapper):
            t = t[len(wrapper):-1]
    if v is None:
        return None
    if t.startswith(("INT", "UINT", "BIGINT", "HUGEINT", "SMALLINT", "TINYINT", "INTEGER", "UBIGINT")):
        return int(v)
    if t.startswith(("DECIMAL", "FLOAT", "DOUBLE", "REAL", "NUMERIC")):
        return decimal.Decimal(str(v))
    return v


def normalise_rows(rows: list[list], types: list[str]) -> list[str]:
    return ["|".join(_norm(typed_value(v, t)) for v, t in zip(r, types)) for r in rows]


def checksum(lines: list[str]) -> str:
    """Order-insensitive SHA-256 of the normalised result (first 16 hex chars)."""
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()[:16]


def query_sql(engine: str, qid: int) -> str:
    return (ROOT / "queries" / engine / f"q{qid:02d}.sql").read_text()
