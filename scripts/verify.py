"""Stage 1 gate: are the query results correct before anything is timed?

1. SF1: each engine's result equals the TPC-H reference answer from DuckDB's
   tpch_answers() (same row order, numbers within 0.01, text exact).
2. Every SF: both engines return the same number of rows and the same checksum
   (values rounded to 2 decimals, order-insensitive SHA-256).
Loads the databases first (untimed) if they are missing.
Writes results/verification.csv; exits non-zero on any mismatch.
"""
from __future__ import annotations

import csv
import decimal
import sys

from common import (CFG, QUERIES, ROOT, ch_http, checksum, docker_client, duck_call, ensure_infra,
                    normalise_rows, query_sql, start_clickhouse, start_duckdb, typed_value)
import load as loadmod

OUT = ROOT / "results" / "verification.csv"
TOL = decimal.Decimal("0.01")


def run_clickhouse(sf: int, qid: int):
    body, _ = ch_http(query_sql("clickhouse", qid), settings={"database": f"tpch_sf{sf}"})
    types = [m["type"] for m in body["meta"]]
    return body["data"], types


def run_duckdb(sf: int, qid: int):
    duck_call({"op": "open", "sf": sf})
    r = duck_call({"op": "query", "sql": query_sql("duckdb", qid)})
    if r["query_error"]:
        raise RuntimeError(r["query_error"])
    return r["rows"], r["types"]


def reference(qid: int) -> list[list[str]]:
    r = duck_call({"op": "sql", "sql": f"SELECT answer FROM tpch_answers() WHERE query_nr={qid} AND scale_factor=1"})
    lines = r["rows"][0][0].strip().split("\n")[1:]  # drop header
    return [ln.split("|") for ln in lines]


def cell_equal(ours, ref: str) -> bool:
    if ours is None:
        return ref in ("", "NULL")
    if isinstance(ours, (int, decimal.Decimal)):
        try:
            return abs(decimal.Decimal(str(ours)) - decimal.Decimal(ref)) <= TOL
        except decimal.InvalidOperation:
            return False
    return str(ours).rstrip()[:10 if len(ref) == 10 and ref[4] == "-" else None] == ref.rstrip()


def matches_reference(rows, types, ref) -> tuple[bool, str]:
    if len(rows) != len(ref):
        return False, f"row count {len(rows)} != reference {len(ref)}"
    for i, (r, e) in enumerate(zip(rows, ref)):
        vals = [typed_value(v, t) for v, t in zip(r, types)]
        if len(vals) != len(e):
            return False, f"row {i}: {len(vals)} columns != {len(e)}"
        for j, (v, x) in enumerate(zip(vals, e)):
            if not cell_equal(v, x):
                return False, f"row {i} col {j}: {v!r} != reference {x!r}"
    return True, ""


def ensure_loaded(sf: int) -> None:
    have = ch_http(f"SELECT count() FROM system.tables WHERE database='tpch_sf{sf}'", fmt="TSV")[0].strip()
    if have != str(len(CFG["data"]["tables"])):
        print(f"loading ClickHouse sf{sf} (untimed)", flush=True)
        loadmod.load_clickhouse(sf, DC.containers.get(CFG["engines"]["clickhouse"]["container"]))
    try:
        duck_call({"op": "open", "sf": sf})
        n = duck_call({"op": "query", "sql": "SELECT count(*) FROM duckdb_tables()"})["rows"][0][0]
    except Exception:
        n = 0
    if n != len(CFG["data"]["tables"]):
        print(f"loading DuckDB sf{sf} (untimed)", flush=True)
        loadmod.load_duckdb(sf, DC.containers.get(CFG["engines"]["duckdb"]["container"]))


def main() -> int:
    global DC
    DC = docker_client()
    ensure_infra(DC)
    start_clickhouse(DC)
    start_duckdb(DC)
    ok_all = True
    rows_out = []
    for sf in CFG["data"]["scale_factors"]:
        ensure_loaded(sf)
        for q in QUERIES:
            qid = q["id"]
            res = {}
            for engine, fn in (("clickhouse", run_clickhouse), ("duckdb", run_duckdb)):
                try:
                    rows, types = fn(sf, qid)
                    res[engine] = (rows, types, checksum(normalise_rows(rows, types)), "")
                except Exception as e:
                    res[engine] = ([], [], "", f"{type(e).__name__}: {e}"[:300])
            same = (len(res["clickhouse"][0]) == len(res["duckdb"][0])
                    and res["clickhouse"][2] == res["duckdb"][2] != "")
            for engine in ("clickhouse", "duckdb"):
                rows, types, cs, err = res[engine]
                ref_ok, why = ("", "")
                if sf == 1 and not err:
                    ref_ok, why = matches_reference(rows, types, reference(qid))
                ok = not err and same and (ref_ok is True or sf != 1)
                ok_all &= ok
                rows_out.append(dict(sf=sf, query_id=qid, engine=engine, rows_returned=len(rows),
                                     result_checksum=cs, matches_reference=ref_ok if sf == 1 else "n/a",
                                     matches_other_engine=same, detail=err or why))
                print(f"{'PASS' if ok else 'FAIL'} sf{sf:<3d} q{qid:02d} {engine:10s} rows={len(rows):4d} "
                      f"cs={cs} ref={ref_ok if sf == 1 else 'n/a'} cross={same} {err or why}", flush=True)
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    print("ALL PASS" if ok_all else "SOME FAILED")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
