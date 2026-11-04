"""Stage 1: generate TPC-H data with DuckDB's dbgen and export each table to Parquet.

Runs in the driver image with the Parquet volume mounted at /data.
Writes /data/sf{sf}/{table}.parquet and results/data_manifest.json.
Gate: every table's row count equals the TPC-H specification.
"""
import json
import sys
import time
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
TABLES = CFG["data"]["tables"]

# TPC-H spec, clause 4.2.5: fixed or SF-proportional cardinalities.
# lineitem is not exactly proportional; values are those of the reference dbgen.
LINEITEM = {1: 6001215, 10: 59986052, 3: 18000048}


def expected_rows(table: str, sf: int) -> int:
    per_sf = {"supplier": 10_000, "customer": 150_000, "part": 200_000,
              "partsupp": 800_000, "orders": 1_500_000}
    if table == "region":
        return 5
    if table == "nation":
        return 25
    if table == "lineitem":
        return LINEITEM[sf]
    return per_sf[table] * sf


def generate(sf: int) -> dict:
    out = Path(f"/data/sf{sf}")
    out.mkdir(parents=True, exist_ok=True)
    scratch = Path(f"/tmp/gen_sf{sf}.duckdb")
    scratch.unlink(missing_ok=True)
    con = duckdb.connect(str(scratch))
    con.execute("SET memory_limit='6GiB'; SET temp_directory='/tmp/gen_spill'")
    con.execute("LOAD tpch")
    t0 = time.time()
    con.execute(f"CALL dbgen(sf={sf})")
    gen_s = time.time() - t0
    info = {"sf": sf, "dbgen_s": round(gen_s, 1), "tables": {}}
    for t in TABLES:
        f = out / f"{t}.parquet"
        con.execute(f"COPY {t} TO '{f}' (FORMAT parquet)")
        n_db = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        n_pq = con.execute(f"SELECT count(*) FROM read_parquet('{f}')").fetchone()[0]
        info["tables"][t] = {"rows": n_pq, "rows_in_db": n_db, "expected": expected_rows(t, sf),
                             "bytes": f.stat().st_size}
    info["schema"] = {
        t: con.execute(f"SELECT column_name, data_type FROM information_schema.columns "
                       f"WHERE table_name='{t}' ORDER BY ordinal_position").fetchall()
        for t in TABLES
    }
    con.close()
    scratch.unlink(missing_ok=True)
    return info


def main(sfs):
    manifest_p = ROOT / "results" / "data_manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    manifest["duckdb_version"] = duckdb.__version__
    ok = True
    for sf in sfs:
        info = generate(sf)
        manifest[f"sf{sf}"] = info
        for t, d in info["tables"].items():
            good = d["rows"] == d["expected"] == d["rows_in_db"]
            ok &= good
            print(f"{'PASS' if good else 'FAIL'} sf{sf} {t:9s} rows={d['rows']:>10,} expected={d['expected']:>10,} {d['bytes']/1e6:9.1f} MB")
        manifest_p.write_text(json.dumps(manifest, indent=2) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main([int(a) for a in sys.argv[1:]] or CFG["data"]["scale_factors"]))
