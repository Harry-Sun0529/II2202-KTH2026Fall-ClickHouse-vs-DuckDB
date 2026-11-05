"""Stage 2 gate: completeness and sanity of results/raw_runs.csv and load_runs.csv.

1. Complete: 2 engines x 2 SF x 8 queries x (1 cold + 20 warm) = 672 run rows,
   2 x 2 x 3 = 12 load rows, each block with run_idx 0..20 exactly once.
2. Correct: every run without an error returned the verified checksum.
3. Sane: latency > 0; peak memory <= 8 GiB; SF10 warm median >= SF1 warm median.
Violations are listed (never deleted). Writes results/stats/gate2.json.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
LIMIT = 8 * 1024 ** 3


def main() -> int:
    runs = pd.read_csv(ROOT / "results/raw_runs.csv", keep_default_na=False)
    loads = pd.read_csv(ROOT / "results/load_runs.csv", keep_default_na=False)
    engines, sfs, qids = ["clickhouse", "duckdb"], CFG["data"]["scale_factors"], [q["id"] for q in CFG["queries"]]
    n_runs = 1 + CFG["repetitions"]["warm"]
    issues, notes = [], []

    exp_runs = len(engines) * len(sfs) * len(qids) * n_runs
    exp_loads = len(engines) * len(sfs) * CFG["repetitions"]["load"]
    if len(runs) != exp_runs:
        issues.append(f"raw_runs has {len(runs)} rows, expected {exp_runs}")
    if len(loads) != exp_loads:
        issues.append(f"load_runs has {len(loads)} rows, expected {exp_loads}")
    for e in engines:
        for sf in sfs:
            for q in qids:
                b = runs[(runs.engine == e) & (runs.sf == sf) & (runs.query_id == q)]
                if sorted(b.run_idx.astype(int)) != list(range(n_runs)):
                    issues.append(f"{e} sf{sf} q{q}: run_idx {sorted(b.run_idx.astype(int))}")
                if (b[b.run_idx.astype(int) == 0].phase != "cold").any() or (b[b.run_idx.astype(int) > 0].phase != "warm").any():
                    issues.append(f"{e} sf{sf} q{q}: wrong phase labels")
            nl = len(loads[(loads.engine == e) & (loads.sf == sf)])
            if nl != CFG["repetitions"]["load"]:
                issues.append(f"load {e} sf{sf}: {nl} rows")

    err = runs[runs.error != ""]
    for _, r in err.iterrows():
        notes.append(f"run error: {r.engine} sf{r.sf} q{r.query_id} run{r.run_idx}: {r.error[:120]}")
    ok = runs[runs.error == ""].copy()
    bad_cs = ok[ok.result_ok.astype(str) != "True"]
    for _, r in bad_cs.iterrows():
        issues.append(f"wrong checksum: {r.engine} sf{r.sf} q{r.query_id} run{r.run_idx}")
    lat = pd.to_numeric(ok.latency_ms)
    if (lat <= 0).any():
        issues.append(f"{int((lat <= 0).sum())} runs with latency <= 0")
    peak = pd.to_numeric(runs.peak_mem_bytes)
    if (peak > LIMIT).any():
        issues.append(f"{int((peak > LIMIT).sum())} runs with peak > 8 GiB")
    for _, r in loads[loads.error != ""].iterrows():
        notes.append(f"load error: {r.engine} sf{r.sf} rep{r.rep}: {r.error[:120]}")

    ok["latency_ms"] = lat
    med = ok[ok.phase == "warm"].groupby(["engine", "query_id", "sf"]).latency_ms.median().unstack("sf")
    scale = []
    for (e, q), row in med.iterrows():
        lo, hi = row.get(min(sfs)), row.get(max(sfs))
        good = bool(pd.notna(lo) and pd.notna(hi) and hi >= lo)
        scale.append({"engine": e, "query_id": int(q), "sf1_ms": lo, "sf10_ms": hi, "ok": good})
        if not good:
            issues.append(f"SF{max(sfs)} median < SF{min(sfs)} median: {e} q{q}")

    report = {"rows": len(runs), "loads": len(loads), "errors": len(err), "issues": issues, "notes": notes,
              "max_peak_gib": float(peak.max() / 1024 ** 3), "scaling": scale}
    out = ROOT / "results/stats/gate2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=float) + "\n")
    print(f"rows={len(runs)} loads={len(loads)} errors={len(err)} max_peak={report['max_peak_gib']:.2f} GiB")
    for n in notes:
        print("NOTE ", n)
    for i in issues:
        print("ISSUE", i)
    print("GATE 2 PASS" if not issues else "GATE 2: issues to explain")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
