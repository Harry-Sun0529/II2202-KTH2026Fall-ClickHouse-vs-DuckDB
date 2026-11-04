"""Stage 2 (RQ2/RQ3): timed loads from Parquet into each engine's native storage.

For every SF and engine, `repetitions.load` times:
  stop engine -> drop VM page cache -> start engine -> drop database -> import -> time.
ClickHouse: INSERT INTO t SELECT * FROM file(...parquet) into MergeTree tables
ordered by the TPC-H primary key, then OPTIMIZE ... FINAL (timed separately).
DuckDB: CREATE TABLE t AS SELECT * FROM read_parquet(...), then CHECKPOINT
(timed separately). Footprint: active parts' bytes_on_disk / .duckdb file size.

One row per load in results/load_runs.csv. The last load of each engine x SF is
the database that the query benchmark uses.
"""
from __future__ import annotations

import csv
import sys
import traceback

from common import (CFG, CH, DK, TABLES, CgroupSampler, ch_http, docker_client, drop_page_cache,
                    duck_call, ensure_infra, now_iso, restart_engine, start_clickhouse, start_duckdb, ROOT)

LOAD_CSV = ROOT / "results" / "load_runs.csv"
LOAD_COLS = ["timestamp", "engine", "engine_version", "sf", "rep", "load_s", "finalize_s", "total_s",
             "disk_bytes", "peak_mem_bytes", "watermark_bytes", "rows_total", "parts_after_load",
             "parts_after_finalize", "error"]

CH_TYPES = {"INTEGER": "Int32", "BIGINT": "Int64", "DATE": "Date", "VARCHAR": "String"}
PRIMARY_KEY = {
    "region": "r_regionkey", "nation": "n_nationkey", "supplier": "s_suppkey",
    "customer": "c_custkey", "part": "p_partkey", "partsupp": "(ps_partkey, ps_suppkey)",
    "orders": "o_orderkey", "lineitem": "(l_orderkey, l_linenumber)",
}


def ch_type(duck_type: str) -> str:
    if duck_type.startswith("DECIMAL"):
        return "Decimal" + duck_type[len("DECIMAL"):]
    return CH_TYPES[duck_type]


def ch_ddl(sf: int) -> list[str]:
    import json
    schema = json.loads((ROOT / "results" / "data_manifest.json").read_text())[f"sf{sf}"]["schema"]
    db = f"tpch_sf{sf}"
    out = []
    for t in TABLES:
        cols = ",\n  ".join(f"{c} {ch_type(ty)}" for c, ty in schema[t])
        out.append(f"CREATE TABLE {db}.{t} (\n  {cols}\n) ENGINE = MergeTree ORDER BY {PRIMARY_KEY[t]}")
    return out


def ch_version() -> str:
    return ch_http("SELECT version()", fmt="TSV")[0].strip()


def ch_parts(db: str) -> int:
    return int(ch_http(f"SELECT count() FROM system.parts WHERE database='{db}' AND active", fmt="TSV")[0])


def load_clickhouse(sf: int, container) -> dict:
    db = f"tpch_sf{sf}"
    ch_http(f"DROP DATABASE IF EXISTS {db} SYNC", fmt="TSV")
    ch_http(f"CREATE DATABASE {db}", fmt="TSV")
    for ddl in ch_ddl(sf):
        ch_http(ddl, fmt="TSV")
    with CgroupSampler(container.id, CFG["memory_sampler"]["interval_ms"]) as s:
        load_ms = 0.0
        for t in TABLES:
            _, ms = ch_http(f"INSERT INTO {db}.{t} SELECT * FROM file('tpch/sf{sf}/{t}.parquet', Parquet)", fmt="TSV")
            load_ms += ms
        parts_load = ch_parts(db)
        fin_ms = 0.0
        for t in TABLES:
            _, ms = ch_http(f"OPTIMIZE TABLE {db}.{t} FINAL", fmt="TSV")
            fin_ms += ms
    parts_fin = ch_parts(db)
    disk = int(ch_http(f"SELECT sum(bytes_on_disk) FROM system.parts WHERE database='{db}' AND active", fmt="TSV")[0])
    rows = int(ch_http(f"SELECT sum(rows) FROM system.parts WHERE database='{db}' AND active", fmt="TSV")[0])
    return dict(load_s=load_ms / 1000, finalize_s=fin_ms / 1000, disk_bytes=disk, rows_total=rows,
                peak_mem_bytes=s.max_current, watermark_bytes=s.watermark,
                parts_after_load=parts_load, parts_after_finalize=parts_fin)


def load_duckdb(sf: int, container) -> dict:
    with CgroupSampler(container.id, CFG["memory_sampler"]["interval_ms"]) as s:
        r = duck_call({"op": "load", "sf": sf})
    return dict(load_s=r["load_s"], finalize_s=r["checkpoint_s"], disk_bytes=r["disk_bytes"] + r["wal_bytes"],
                rows_total=sum(r["rows"].values()), peak_mem_bytes=s.max_current, watermark_bytes=s.watermark,
                parts_after_load="", parts_after_finalize="")


def engine_order(sf: int) -> list[str]:
    # Alternate which engine goes first so slow drift of the machine is spread over both.
    return ["clickhouse", "duckdb"] if sf == min(CFG["data"]["scale_factors"]) else ["duckdb", "clickhouse"]


def main(sfs=None, reps=None) -> int:
    sfs = sfs or CFG["data"]["scale_factors"]
    reps = reps or CFG["repetitions"]["load"]
    dc = docker_client()
    ensure_infra(dc)
    new = not LOAD_CSV.exists()
    with LOAD_CSV.open("a", newline="") as fh:
        w = csv.DictWriter(fh, LOAD_COLS)
        if new:
            w.writeheader()
        for sf in sfs:
            for engine in engine_order(sf):
                c = start_clickhouse(dc) if engine == "clickhouse" else start_duckdb(dc)
                version = ch_version() if engine == "clickhouse" else DK["version"]
                for rep in range(1, reps + 1):
                    c = restart_engine(dc, engine, drop_cache=True)
                    row = dict(timestamp=now_iso(), engine=engine, engine_version=version, sf=sf, rep=rep, error="")
                    try:
                        res = load_clickhouse(sf, c) if engine == "clickhouse" else load_duckdb(sf, c)
                        res["total_s"] = res["load_s"] + res["finalize_s"]
                        row.update(res)
                    except Exception as e:  # failures are results, not retried
                        row["error"] = f"{type(e).__name__}: {e}"[:300]
                        traceback.print_exc()
                    w.writerow(row)
                    fh.flush()
                    print(f"load {engine:10s} sf{sf:<3d} rep{rep} load={row.get('load_s', float('nan')):.2f}s "
                          f"final={row.get('finalize_s', float('nan')):.2f}s disk={row.get('disk_bytes', 0)/1e9:.3f}GB "
                          f"peak={row.get('peak_mem_bytes', 0)/2**30:.2f}GiB err={row['error']}", flush=True)
                c.stop(timeout=30)
    return 0


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    sys.exit(main(sfs=args or None))
