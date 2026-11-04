"""Stage 2 (RQ1/RQ2): query latency and peak memory.

For every SF, engine and query (query order shuffled with the recorded seed):
  stop engine -> drop VM page cache -> start engine     (cold state)
  run 1 = phase "cold"; then 20 consecutive runs = phase "warm".
During every run the driver samples the engine container's cgroup
(memory.current and memory.stat:anon, every 2 ms) and reads the kernel's exact
memory.peak watermark, reset just before the query. The engine's own number is
logged as well: ClickHouse system.query_log.memory_usage, DuckDB process RSS.

One row per run in results/raw_runs.csv. Failures (errors, timeouts, OOM kills)
are recorded, not retried. Re-running resumes: complete blocks are skipped.
"""
from __future__ import annotations

import csv
import json
import random
import sys
import time
import traceback
import uuid
from collections import defaultdict

from common import (CFG, CH, DK, QCLASS, QUERIES, ROOT, CgroupSampler, ch_http, checksum, container_state,
                    docker_client, duck_call, ensure_infra, normalise_rows, now_iso, query_sql, restart_engine,
                    start_clickhouse, start_duckdb)
from load import ch_version, engine_order

RAW_CSV = ROOT / "results" / "raw_runs.csv"
COLS = ["timestamp", "engine", "engine_version", "sf", "query_id", "query_class", "run_idx", "phase",
        "latency_ms", "peak_mem_bytes", "rows_returned", "result_checksum", "error",
        # supplementary columns
        "result_ok", "server_latency_ms", "engine_peak_bytes", "watermark_bytes", "peak_anon_bytes",
        "baseline_mem_bytes", "spill_bytes", "n_samples"]
TIMEOUT_S = 900
INTERVAL = CFG["memory_sampler"]["interval_ms"]


def expected_checksums() -> dict:
    exp = {}
    with (ROOT / "results" / "verification.csv").open() as fh:
        for r in csv.DictReader(fh):
            exp[(int(r["sf"]), int(r["query_id"]), r["engine"])] = r["result_checksum"]
    return exp


def done_blocks() -> dict:
    n = defaultdict(int)
    if RAW_CSV.exists():
        with RAW_CSV.open() as fh:
            for r in csv.DictReader(fh):
                n[(r["engine"], int(r["sf"]), int(r["query_id"]))] += 1
    return n


def run_clickhouse(sf, qid, container):
    qid_str = f"ii2202-{uuid.uuid4()}"
    out = {"query_uuid": qid_str}
    with CgroupSampler(container.id, INTERVAL) as s:
        base = s.baseline()
        try:
            body, ms = ch_http(query_sql("clickhouse", qid), query_id=qid_str, timeout=TIMEOUT_S + 60,
                               settings={"database": f"tpch_sf{sf}", "max_execution_time": TIMEOUT_S})
            types = [m["type"] for m in body["meta"]]
            out.update(latency_ms=ms, rows=body["data"], types=types, error="")
        except Exception as e:
            out.update(latency_ms=None, rows=[], types=[], error=f"{type(e).__name__}: {e}"[:300])
    out.update(peak=s.max_current, anon=s.max_anon, watermark=s.watermark, n=s.n, base=base)
    return out


def run_duckdb(sf, qid, container):
    with CgroupSampler(container.id, INTERVAL) as s:
        base = s.baseline()
        try:
            r = duck_call({"op": "query", "sql": query_sql("duckdb", qid), "timeout_s": TIMEOUT_S},
                          timeout=TIMEOUT_S + 60)
            err = r["query_error"] or ""
            out = dict(latency_ms=r["latency_ms"], rows=r["rows"], types=r["types"], error=err,
                       engine_peak=r["rss_peak"], spill=r["spill_peak"], server_ms=r["latency_ms"])
        except Exception as e:
            out = dict(latency_ms=None, rows=[], types=[], error=f"{type(e).__name__}: {e}"[:300])
    out.update(peak=s.max_current, anon=s.max_anon, watermark=s.watermark, n=s.n, base=base)
    return out


def clickhouse_log(uuids: list[str]) -> dict:
    """Server-side duration, memory_usage and spill bytes from system.query_log."""
    ch_http("SYSTEM FLUSH LOGS", fmt="TSV")
    ids = ",".join(f"'{u}'" for u in uuids)
    body, _ = ch_http(
        "SELECT query_id, query_duration_ms, memory_usage, "
        "ProfileEvents['ExternalProcessingCompressedBytesTotal'] AS spill "
        f"FROM system.query_log WHERE query_id IN ({ids}) AND type != 'QueryStart'")
    return {r[0]: dict(server_ms=float(r[1]), engine_peak=int(r[2]), spill=int(r[3])) for r in body["data"]}


def record(engine, version, sf, qid, run_idx, res, expected) -> dict:
    cs = checksum(normalise_rows(res["rows"], res["types"])) if not res["error"] else ""
    return dict(
        timestamp=res["ts"], engine=engine, engine_version=version, sf=sf, query_id=qid,
        query_class=QCLASS[qid], run_idx=run_idx, phase="cold" if run_idx == 0 else "warm",
        latency_ms=round(res["latency_ms"], 3) if res["latency_ms"] is not None else "",
        peak_mem_bytes=res["peak"], rows_returned=len(res["rows"]) if not res["error"] else "",
        result_checksum=cs, error=res["error"],
        result_ok=(cs == expected) if not res["error"] else False,
        server_latency_ms=res.get("server_ms", ""), engine_peak_bytes=res.get("engine_peak", ""),
        watermark_bytes=res["watermark"], peak_anon_bytes=res["anon"], baseline_mem_bytes=res["base"],
        spill_bytes=res.get("spill", ""), n_samples=res["n"],
    )


def run_block(dc, engine, version, sf, qid, expected, n_warm, writer, fh):
    c = restart_engine(dc, engine, drop_cache=True)
    if engine == "duckdb":
        duck_call({"op": "open", "sf": sf})
    runner = run_clickhouse if engine == "clickhouse" else run_duckdb
    results = []
    for i in range(1 + n_warm):
        ts = now_iso()
        res = runner(sf, qid, c)
        res["ts"] = ts
        if res["error"]:
            st = container_state(dc, engine)
            if not st["Running"]:  # killed (e.g. OOM): note it and bring the engine back
                res["error"] += f" | container exited, OOMKilled={st['OOMKilled']}, exit={st['ExitCode']}"
                c = restart_engine(dc, engine, drop_cache=False)
                if engine == "duckdb":
                    duck_call({"op": "open", "sf": sf})
        results.append(res)
    if engine == "clickhouse":
        log = clickhouse_log([r["query_uuid"] for r in results])
        for r in results:
            r.update(log.get(r["query_uuid"], {}))
    rows = [record(engine, version, sf, qid, i, r, expected) for i, r in enumerate(results)]
    writer.writerows(rows)
    fh.flush()
    lat = [r["latency_ms"] for r in rows[1:] if r["latency_ms"] != ""]
    med = sorted(lat)[len(lat) // 2] if lat else float("nan")
    bad = sum(1 for r in rows if not r["result_ok"])
    print(f"{engine:10s} sf{sf:<3d} q{qid:02d} cold={rows[0]['latency_ms']}ms warm_med={med:.1f}ms "
          f"peak={max(r['peak_mem_bytes'] for r in rows)/2**30:.2f}GiB not_ok={bad}", flush=True)


def main(sfs=None, n_warm=None, only_queries=None) -> int:
    sfs = sfs or CFG["data"]["scale_factors"]
    n_warm = CFG["repetitions"]["warm"] if n_warm is None else n_warm
    expected = expected_checksums()
    dc = docker_client()
    ensure_infra(dc)
    have = done_blocks()
    new = not RAW_CSV.exists()
    settings = {}
    with RAW_CSV.open("a", newline="") as fh:
        w = csv.DictWriter(fh, COLS)
        if new:
            w.writeheader()
        for sf in sfs:
            for k, engine in enumerate(engine_order(sf)):
                if engine == "clickhouse":
                    start_clickhouse(dc)
                    version = ch_version()
                    body, _ = ch_http("SELECT name, value FROM system.settings WHERE name IN ('max_threads',"
                                      "'max_bytes_before_external_group_by','max_bytes_before_external_sort',"
                                      "'max_memory_usage','join_algorithm','use_query_cache',"
                                      "'use_query_condition_cache','max_bytes_ratio_before_external_group_by',"
                                      "'max_bytes_ratio_before_external_sort')")
                    srv, _ = ch_http("SELECT name, value FROM system.server_settings WHERE name="
                                     "'max_server_memory_usage'")
                    settings["clickhouse"] = dict(body["data"] + srv["data"]) | {"version": version}
                else:
                    start_duckdb(dc)
                    version = DK["version"]
                    settings["duckdb"] = duck_call({"op": "open", "sf": sf})["settings"] | {"version": version}
                qids = [q["id"] for q in QUERIES if not only_queries or q["id"] in only_queries]
                random.Random(CFG["seed"] + 1000 * sf + k).shuffle(qids)
                print(f"== {engine} sf{sf} order {qids}", flush=True)
                for qid in qids:
                    if have[(engine, sf, qid)] >= 1 + n_warm:
                        continue
                    try:
                        run_block(dc, engine, version, sf, qid, expected[(sf, qid, engine)], n_warm, w, fh)
                    except Exception:
                        traceback.print_exc()
                dc.containers.get(CH["container"] if engine == "clickhouse" else DK["container"]).stop(timeout=30)
    (ROOT / "results" / "engine_settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
