"""Stage 3: EDA and statistics. Reads results/*.csv, writes results/stats/*.csv.

Every number quoted in the report is taken from one of the files written here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats as sps

import stats as S

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stats"
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
SFS = CFG["data"]["scale_factors"]
QORDER = [q["id"] for q in CFG["queries"]]
QCLASS = {q["id"]: q["class"] for q in CFG["queries"]}
ENGINES = ["clickhouse", "duckdb"]
GIB = 1024 ** 3
NS = (3, 5, 10, 15, 20)


def load_runs() -> pd.DataFrame:
    r = pd.read_csv(ROOT / "results/raw_runs.csv", keep_default_na=False)
    for c in ["latency_ms", "peak_mem_bytes", "watermark_bytes", "peak_anon_bytes", "baseline_mem_bytes",
              "engine_peak_bytes", "spill_bytes", "server_latency_ms", "n_samples"]:
        r[c] = pd.to_numeric(r[c], errors="coerce")
    r["ok"] = (r.error == "") & (r.result_ok.astype(str) == "True")
    return r


def summary(r: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (e, sf, q), b in r.groupby(["engine", "sf", "query_id"]):
        b = b.sort_values("run_idx")
        warm = b[(b.phase == "warm") & b.ok]
        cold = b[b.phase == "cold"].iloc[0]
        w = warm.latency_ms.to_numpy()
        m, lo, hi = S.bootstrap_median_ci(w)
        widths = S.halfwidth_vs_n(w, NS)
        rows.append(dict(
            engine=e, sf=sf, query_id=q, query_class=QCLASS[q],
            n_warm_ok=len(w), n_errors=int((b.error != "").sum()),
            cold_ms=cold.latency_ms if cold.ok else np.nan, cold_error=cold.error,
            warm_median_ms=m, ci_lo_ms=lo, ci_hi_ms=hi,
            warm_q1_ms=np.quantile(w, 0.25), warm_q3_ms=np.quantile(w, 0.75),
            warm_min_ms=w.min(), warm_max_ms=w.max(),
            cv_warm=S.cv(w), skew_warm=float(sps.skew(w)), shapiro_p=S.shapiro_p(w),
            cold_over_warm=(cold.latency_ms / m) if cold.ok else np.nan,
            rel_halfwidth_20=widths.get(20, np.nan), min_n_5pct=S.min_n_for(widths),
            peak_median_bytes=warm.peak_mem_bytes.median(), peak_max_bytes=b.peak_mem_bytes.max(),
            peak_cold_bytes=cold.peak_mem_bytes,
            watermark_max_bytes=b.watermark_bytes.max(), anon_peak_median_bytes=warm.peak_anon_bytes.median(),
            engine_peak_median_bytes=warm.engine_peak_bytes.median(),
            baseline_cold_bytes=cold.baseline_mem_bytes, baseline_warm_median_bytes=warm.baseline_mem_bytes.median(),
            added_peak_median_bytes=(warm.peak_mem_bytes - warm.baseline_mem_bytes).median(),
            spill_max_bytes=b.spill_bytes.max(), server_median_ms=warm.server_latency_ms.median(),
            client_overhead_median_ms=(warm.latency_ms - warm.server_latency_ms).median(),
        ))
    return pd.DataFrame(rows)


def comparison(r: pd.DataFrame, summ: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sf in SFS:
        block = []
        for q in QORDER:
            ch = r[(r.engine == "clickhouse") & (r.sf == sf) & (r.query_id == q) & (r.phase == "warm") & r.ok].latency_ms.to_numpy()
            dk = r[(r.engine == "duckdb") & (r.sf == sf) & (r.query_id == q) & (r.phase == "warm") & r.ok].latency_ms.to_numpy()
            ratio, rlo, rhi = S.bootstrap_ratio_ci(ch, dk)
            u, p = S.mann_whitney(ch, dk)
            d = S.cliffs_delta(ch, dk)
            sc = summ.set_index(["engine", "sf", "query_id"])
            block.append(dict(sf=sf, query_id=q, query_class=QCLASS[q],
                              ch_median_ms=np.median(ch), duck_median_ms=np.median(dk),
                              ratio_ch_over_duck=ratio, ratio_lo=rlo, ratio_hi=rhi,
                              speedup_duck_over_ch=1 / ratio,
                              cold_ratio_ch_over_duck=sc.loc[("clickhouse", sf, q), "cold_ms"] / sc.loc[("duckdb", sf, q), "cold_ms"],
                              mw_u=u, p=p, cliffs_delta=d, magnitude=S.cliffs_magnitude(d),
                              faster="clickhouse" if ratio < 1 else "duckdb",
                              peak_ratio_ch_over_duck=sc.loc[("clickhouse", sf, q), "peak_median_bytes"] / sc.loc[("duckdb", sf, q), "peak_median_bytes"]))
        adj = S.holm([b["p"] for b in block])
        for b, a in zip(block, adj):
            b["p_holm"] = a
            b["significant"] = bool(a < 0.05)
        rows += block
    return pd.DataFrame(rows)


def scaling(r: pd.DataFrame) -> pd.DataFrame:
    rows = []
    lo_sf, hi_sf = min(SFS), max(SFS)
    for e in ENGINES:
        for q in QORDER:
            sel = lambda sf: r[(r.engine == e) & (r.sf == sf) & (r.query_id == q) & (r.phase == "warm") & r.ok].latency_ms.to_numpy()
            b, lo, hi = S.loglog_slope(lo_sf, sel(lo_sf), hi_sf, sel(hi_sf))
            rows.append(dict(engine=e, query_id=q, query_class=QCLASS[q], slope_b=b, b_lo=lo, b_hi=hi,
                             ratio_sf10_over_sf1=np.median(sel(hi_sf)) / np.median(sel(lo_sf))))
    return pd.DataFrame(rows)


def load_summary(loads: pd.DataFrame, summ: pd.DataFrame) -> pd.DataFrame:
    manifest = json.loads((ROOT / "results/data_manifest.json").read_text())
    rows = []
    for (e, sf), b in loads.groupby(["engine", "sf"]):
        b = b[b.error == ""]
        parquet = sum(t["bytes"] for t in manifest[f"sf{sf}"]["tables"].values())
        idle = summ[(summ.engine == e) & (summ.sf == sf)].baseline_cold_bytes
        rows.append(dict(
            engine=e, sf=sf, n_loads=len(b),
            load_median_s=b.load_s.median(), load_min_s=b.load_s.min(), load_max_s=b.load_s.max(),
            finalize_median_s=b.finalize_s.median(), total_median_s=b.total_s.median(),
            total_min_s=b.total_s.min(), total_max_s=b.total_s.max(),
            disk_median_bytes=b.disk_bytes.median(), disk_min_bytes=b.disk_bytes.min(), disk_max_bytes=b.disk_bytes.max(),
            parquet_bytes=parquet, disk_over_parquet=b.disk_bytes.median() / parquet,
            load_peak_median_bytes=b.peak_mem_bytes.median(), load_peak_max_bytes=b.peak_mem_bytes.max(),
            load_anon_peak_median_bytes=b.peak_anon_bytes.median(), load_anon_peak_max_bytes=b.peak_anon_bytes.max(),
            rows_total=int(b.rows_total.iloc[0]) if len(b) else np.nan,
            idle_after_restart_median_bytes=idle.median(),
        ))
    return pd.DataFrame(rows)


def breakeven(r: pd.DataFrame, loads: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sf in SFS:
        for basis in ("total_s", "load_s"):
            L = {e: loads[(loads.engine == e) & (loads.sf == sf) & (loads.error == "")][basis].to_numpy() for e in ENGINES}
            runs = {e: [r[(r.engine == e) & (r.sf == sf) & (r.query_id == q) & (r.phase == "warm") & r.ok].latency_ms.to_numpy() / 1000
                        for q in QORDER] for e in ENGINES}
            point, lo, hi, share = S.break_even_bootstrap(L["clickhouse"], runs["clickhouse"], L["duckdb"], runs["duckdb"])
            q = {e: float(sum(np.median(x) for x in runs[e])) for e in ENGINES}
            rows.append(dict(sf=sf, load_basis=basis, L_ch_s=float(np.median(L["clickhouse"])),
                             L_duck_s=float(np.median(L["duckdb"])), q_ch_s=q["clickhouse"], q_duck_s=q["duckdb"],
                             n_star=point.n_star, kind=point.kind.replace("a_", "clickhouse_").replace("b_", "duckdb_"),
                             n_star_lo=lo, n_star_hi=hi, share_crossing=share))
    return pd.DataFrame(rows)


def repetitions(r: pd.DataFrame):
    rows = []
    for (e, sf, q), b in r[(r.phase == "warm") & r.ok].sort_values("run_idx").groupby(["engine", "sf", "query_id"]):
        for n, w in S.halfwidth_vs_n(b.latency_ms.to_numpy(), NS).items():
            rows.append(dict(engine=e, sf=sf, query_id=q, n=n, rel_halfwidth=w))
    d = pd.DataFrame(rows)
    agg = d.groupby("n").rel_halfwidth.agg(
        median="median", q1=lambda x: x.quantile(0.25), q3=lambda x: x.quantile(0.75), max="max",
        share_below_5pct=lambda x: (x < 0.05).mean(), share_below_2pct=lambda x: (x < 0.02).mean()).reset_index()
    by_engine = d.groupby(["engine", "n"]).rel_halfwidth.agg(
        median="median", max="max", share_below_5pct=lambda x: (x < 0.05).mean()).reset_index()
    return d, agg, by_engine


def pca_tables(summ: pd.DataFrame):
    cols, data = [], []
    for e in ENGINES:
        for sf in SFS:
            s = summ[(summ.engine == e) & (summ.sf == sf)].set_index("query_id").loc[QORDER]
            data.append(np.log(s.warm_median_ms.to_numpy())); cols.append(f"lat_{e}_sf{sf}")
            data.append(np.log(s.peak_median_bytes.to_numpy())); cols.append(f"mem_{e}_sf{sf}")
    X = np.column_stack(data)
    scores, loadings, ratio = S.pca(X)
    sc = pd.DataFrame({"query_id": QORDER, "query_class": [QCLASS[q] for q in QORDER],
                       "pc1": scores[:, 0], "pc2": scores[:, 1]})
    ld = pd.DataFrame({"feature": cols, "pc1": loadings[:, 0], "pc2": loadings[:, 1]})
    var = pd.DataFrame({"component": [f"pc{i+1}" for i in range(len(ratio))], "explained": ratio})
    return sc, ld, var


def memory_check(r: pd.DataFrame) -> pd.DataFrame:
    """How well the sampled cgroup maximum agrees with the kernel's exact watermark."""
    v = r.dropna(subset=["watermark_bytes"])
    rel = (v.watermark_bytes - v.peak_mem_bytes) / v.watermark_bytes
    interval = v.latency_ms / v.n_samples
    return pd.DataFrame([dict(
        runs=len(v), median_rel_gap=rel.median(), p95_rel_gap=rel.quantile(0.95), max_rel_gap=rel.max(),
        share_gap_below_1pct=(rel < 0.01).mean(), median_interval_ms=interval.median(),
        p95_interval_ms=interval.quantile(0.95), max_interval_ms=interval.max())])


def expectations(summ, comp, scal, ls, be) -> pd.DataFrame:
    warm = summ
    rows = [
        dict(id="E1", expectation="Latency positive and right-skewed (long tail)",
             metric="share of combos with skewness > 0", value=float((warm.skew_warm > 0).mean())),
        dict(id="E1b", expectation="Latency positive and right-skewed (long tail)",
             metric="median max/median ratio of warm runs", value=float((warm.warm_max_ms / warm.warm_median_ms).median())),
        dict(id="E2", expectation="Cold clearly slower than warm",
             metric="share of combos with cold > warm median", value=float((warm.cold_over_warm > 1).mean())),
        dict(id="E2b", expectation="Cold clearly slower than warm",
             metric="median cold/warm ratio", value=float(warm.cold_over_warm.median())),
        dict(id="E3", expectation="Warm CV below 10 %",
             metric="share of combos with CV < 0.10", value=float((warm.cv_warm < 0.10).mean())),
        dict(id="E3b", expectation="Warm CV below 10 %", metric="max CV", value=float(warm.cv_warm.max())),
        dict(id="E4", expectation="Latency roughly linear in SF (log-log slope ~ 1)",
             metric="share of engine x query with 0.8 <= b <= 1.2",
             value=float(((scal.slope_b >= 0.8) & (scal.slope_b <= 1.2)).mean())),
        dict(id="E4b", expectation="Latency roughly linear in SF (log-log slope ~ 1)",
             metric="median slope b", value=float(scal.slope_b.median())),
        dict(id="E5", expectation="ClickHouse faster on join and aggregation queries",
             metric="share of join+aggregation comparisons where ClickHouse is faster",
             value=float((comp[comp.query_class != "scan"].ratio_ch_over_duck < 1).mean())),
        dict(id="E5b", expectation="ClickHouse faster on scan queries (H1 of the plan)",
             metric="share of scan comparisons where ClickHouse is faster",
             value=float((comp[comp.query_class == "scan"].ratio_ch_over_duck < 1).mean())),
        dict(id="E6", expectation="DuckDB loads faster",
             metric="SFs where DuckDB median total load < ClickHouse",
             value=float(sum(ls[(ls.sf == sf) & (ls.engine == "duckdb")].total_median_s.iloc[0] <
                             ls[(ls.sf == sf) & (ls.engine == "clickhouse")].total_median_s.iloc[0] for sf in SFS))),
        dict(id="E7", expectation="DuckDB has lower idle memory",
             metric="SFs where DuckDB idle (after restart) < ClickHouse",
             value=float(sum(ls[(ls.sf == sf) & (ls.engine == "duckdb")].idle_after_restart_median_bytes.iloc[0] <
                             ls[(ls.sf == sf) & (ls.engine == "clickhouse")].idle_after_restart_median_bytes.iloc[0] for sf in SFS))),
        dict(id="E8", expectation="Peak memory grows with SF but stays below 7 GiB",
             metric="max cgroup peak over all runs (GiB)", value=float(summ.peak_max_bytes.max() / GIB)),
        dict(id="E8b", expectation="Peak memory grows with SF but stays below 7 GiB",
             metric="share of engine x query with higher median peak at SF10",
             value=float(np.mean([summ[(summ.engine == e) & (summ.query_id == q) & (summ.sf == max(SFS))].peak_median_bytes.iloc[0] >
                                  summ[(summ.engine == e) & (summ.query_id == q) & (summ.sf == min(SFS))].peak_median_bytes.iloc[0]
                                  for e in ENGINES for q in QORDER]))),
        dict(id="E8c", expectation="Over the limit: spill, not OOM",
             metric="runs with an error", value=float(summ.n_errors.sum())),
        dict(id="E9", expectation="ClickHouse disk footprint <= DuckDB (or similar)",
             metric="SFs where ClickHouse disk < DuckDB disk",
             value=float(sum(ls[(ls.sf == sf) & (ls.engine == "clickhouse")].disk_median_bytes.iloc[0] <
                             ls[(ls.sf == sf) & (ls.engine == "duckdb")].disk_median_bytes.iloc[0] for sf in SFS))),
    ]
    return pd.DataFrame(rows)


def setup_facts() -> pd.DataFrame:
    """Environment and data facts quoted in the report, copied from env.json / data_manifest.json."""
    env = json.loads((ROOT / "results/env.json").read_text())
    man = json.loads((ROOT / "results/data_manifest.json").read_text())
    st = json.loads((ROOT / "results/engine_settings.json").read_text())
    f = {
        "cpu_model": env["host"]["cpu_model"], "host_cores": env["host"]["cpu_cores"],
        "host_perf_cores": env["host"]["cpu_perf_cores"], "host_eff_cores": env["host"]["cpu_eff_cores"],
        "host_mem_gib": env["host"]["mem_total_bytes"] / GIB, "macos": env["host"]["os_version"],
        "docker_version": env["docker"]["server_version"], "docker_vm_mem_mib": env["docker"]["desktop_memory_mib"],
        "docker_vm_cpus": env["docker"]["vm_ncpu"], "kernel": env["docker"]["kernel"],
        "clickhouse_version": st["clickhouse"]["version"], "duckdb_version": st["duckdb"]["version"],
        "ch_max_server_memory_usage": st["clickhouse"]["max_server_memory_usage"],
        "ch_max_threads": st["clickhouse"]["max_threads"],
        "ch_external_group_by": st["clickhouse"]["max_bytes_before_external_group_by"],
        "ch_external_sort": st["clickhouse"]["max_bytes_before_external_sort"],
        "ch_join_algorithm": st["clickhouse"]["join_algorithm"],
        "duck_memory_limit": st["duckdb"]["memory_limit"], "duck_threads": st["duckdb"]["threads"],
        "duck_temp_directory": st["duckdb"]["temp_directory"],
    }
    for sf in SFS:
        t = man[f"sf{sf}"]["tables"]
        f[f"sf{sf}_lineitem_rows"] = t["lineitem"]["rows"]
        f[f"sf{sf}_total_rows"] = sum(v["rows"] for v in t.values())
        f[f"sf{sf}_parquet_bytes"] = sum(v["bytes"] for v in t.values())
    return pd.DataFrame({"key": list(f), "value": list(f.values())})


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    r = load_runs()
    loads = pd.read_csv(ROOT / "results/load_runs.csv", keep_default_na=False)
    for c in ["load_s", "finalize_s", "total_s", "disk_bytes", "peak_mem_bytes", "peak_anon_bytes", "rows_total"]:
        loads[c] = pd.to_numeric(loads[c], errors="coerce")
    summ = summary(r)
    comp = comparison(r, summ)
    scal = scaling(r)
    ls = load_summary(loads, summ)
    be = breakeven(r, loads)
    reps, reps_agg, reps_eng = repetitions(r)
    sc, ld, var = pca_tables(summ)
    files = {"summary": summ, "comparison": comp, "scaling": scal, "load_summary": ls, "breakeven": be,
             "repetitions": reps, "repetitions_summary": reps_agg, "repetitions_by_engine": reps_eng,
             "pca_scores": sc, "pca_loadings": ld, "pca_variance": var, "memory_check": memory_check(r),
             "expectations": expectations(summ, comp, scal, ls, be), "setup": setup_facts()}
    for name, df in files.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    print("wrote", ", ".join(f"{k}.csv" for k in files))


if __name__ == "__main__":
    main()
