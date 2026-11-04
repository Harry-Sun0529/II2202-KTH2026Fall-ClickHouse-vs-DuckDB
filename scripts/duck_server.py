"""DuckDB engine process. Runs inside the DuckDB container (8 GiB / 4 cores).

DuckDB is embedded, so the engine and this small server share one process,
like an application that embeds DuckDB. The driver talks to it with one JSON
line per request over TCP (port 9999). Query latency is measured in-process
around execute + fetchall. A background thread samples this process's RSS
(psutil) and the size of the spill directory.

Ops:
  ping
  open   {sf}                       open /db/tpch_sf{sf}.duckdb with the pragmas
  query  {sql, timeout_s}           -> latency_ms, rows, types, rss_peak, spill_peak
  load   {sf}                       recreate the database from Parquet, timed
  sql    {sql}                      untimed helper (e.g. tpch_answers())
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import shutil
import socketserver
import threading
import time
from pathlib import Path

import duckdb
import psutil
import yaml

CFG = yaml.safe_load(Path("/work/config.yaml").read_text())
PRAGMAS = CFG["engines"]["duckdb"]["pragmas"]
TABLES = CFG["data"]["tables"]
RSS_INTERVAL = CFG["memory_sampler"]["rss_interval_ms"] / 1000
SPILL_DIR = Path(PRAGMAS["temp_directory"])
PROC = psutil.Process()

state = {"con": None, "sf": None}
lock = threading.Lock()


def apply_pragmas(con) -> None:
    SPILL_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET memory_limit='{PRAGMAS['memory_limit']}'")
    con.execute(f"SET threads={int(PRAGMAS['threads'])}")
    con.execute(f"SET temp_directory='{PRAGMAS['temp_directory']}'")


def db_path(sf) -> Path:
    return Path(f"/db/tpch_sf{sf}.duckdb")


def open_db(sf) -> None:
    if state["con"] is not None and state["sf"] == sf:
        return
    if state["con"] is not None:
        state["con"].close()
    con = duckdb.connect(str(db_path(sf)))
    apply_pragmas(con)
    state["con"], state["sf"] = con, sf


def jsonable(v):
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def dir_size(p: Path) -> int:
    total = 0
    try:
        for e in os.scandir(p):
            try:
                total += e.stat(follow_symlinks=False).st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


class RssSampler:
    def __init__(self):
        self.stop = threading.Event()
        self.rss_peak = 0
        self.spill_peak = 0

    def run(self):
        i = 0
        while not self.stop.is_set():
            self.rss_peak = max(self.rss_peak, PROC.memory_info().rss)
            if i % 10 == 0:  # the spill directory is checked every ~50 ms
                self.spill_peak = max(self.spill_peak, dir_size(SPILL_DIR))
            i += 1
            time.sleep(RSS_INTERVAL)

    def __enter__(self):
        self.rss_peak = PROC.memory_info().rss
        self.t = threading.Thread(target=self.run, daemon=True)
        self.t.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.t.join()
        self.rss_peak = max(self.rss_peak, PROC.memory_info().rss)
        self.spill_peak = max(self.spill_peak, dir_size(SPILL_DIR))
        return False


def op_query(req) -> dict:
    con = state["con"]
    timeout = req.get("timeout_s", 3600)
    timer = threading.Timer(timeout, con.interrupt)
    with RssSampler() as s:
        timer.start()
        t0 = time.perf_counter_ns()
        try:
            cur = con.execute(req["sql"])
            rows = cur.fetchall()
            err = None
        except Exception as e:  # out-of-memory, interrupt, ... are results
            rows, cur, err = [], None, f"{type(e).__name__}: {e}"[:500]
        ms = (time.perf_counter_ns() - t0) / 1e6
        timer.cancel()
    types = [str(d[1]) for d in cur.description] if cur is not None else []
    return {
        "latency_ms": ms, "rows": [[jsonable(v) for v in r] for r in rows], "types": types,
        "rss_peak": s.rss_peak, "spill_peak": s.spill_peak, "query_error": err,
        "rss_after": PROC.memory_info().rss,
    }


def op_load(req) -> dict:
    sf = req["sf"]
    if state["con"] is not None:
        state["con"].close()
        state["con"], state["sf"] = None, None
    p = db_path(sf)
    for f in (p, p.with_suffix(".duckdb.wal")):
        f.unlink(missing_ok=True)
    shutil.rmtree(SPILL_DIR, ignore_errors=True)
    con = duckdb.connect(str(p))
    apply_pragmas(con)
    per_table = {}
    with RssSampler() as s:
        t0 = time.perf_counter_ns()
        for t in TABLES:
            t1 = time.perf_counter_ns()
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_parquet('/data/sf{sf}/{t}.parquet')")
            per_table[t] = (time.perf_counter_ns() - t1) / 1e9
        load_s = (time.perf_counter_ns() - t0) / 1e9
        t2 = time.perf_counter_ns()
        con.execute("CHECKPOINT")
        checkpoint_s = (time.perf_counter_ns() - t2) / 1e9
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES}
    con.close()
    wal = p.with_suffix(".duckdb.wal")
    return {
        "load_s": load_s, "checkpoint_s": checkpoint_s, "per_table_s": per_table,
        "disk_bytes": p.stat().st_size, "wal_bytes": wal.stat().st_size if wal.exists() else 0,
        "rows": counts, "rss_peak": s.rss_peak, "spill_peak": s.spill_peak,
    }


def op_sql(req) -> dict:
    con = state["con"] or duckdb.connect()
    con.execute("LOAD tpch")
    cur = con.execute(req["sql"])
    rows = cur.fetchall()
    return {"rows": [[jsonable(v) for v in r] for r in rows], "types": [str(d[1]) for d in cur.description]}


def handle(req) -> dict:
    op = req["op"]
    if op == "ping":
        return {"ok": True, "version": duckdb.__version__, "rss": PROC.memory_info().rss}
    with lock:
        if op == "open":
            open_db(req["sf"])
            settings = state["con"].execute(
                "SELECT name, value FROM duckdb_settings() WHERE name IN "
                "('memory_limit','threads','temp_directory','preserve_insertion_order')").fetchall()
            return {"ok": True, "settings": dict(settings)}
        if op == "query":
            return op_query(req)
        if op == "load":
            return op_load(req)
        if op == "sql":
            return op_sql(req)
    return {"error": f"unknown op {op}"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline()
        try:
            resp = handle(json.loads(line))
        except Exception as e:
            resp = {"error": f"{type(e).__name__}: {e}"[:1000]}
        self.wfile.write((json.dumps(resp) + "\n").encode())


def shutdown(signum, frame):
    # PID 1 in the container: exit promptly on `docker stop` and close the database cleanly.
    if state["con"] is not None:
        state["con"].close()
    os._exit(0)


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGTERM, shutdown)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("0.0.0.0", 9999), Handler) as srv:
        print("duck_server ready", duckdb.__version__, flush=True)
        srv.serve_forever()
