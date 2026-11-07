"""Generate report/numbers.tex, report/tables/*.tex and report/numbers_manifest.csv.

Every data value in main.tex is \\V{key}. This script looks each key up in
results/stats/*.csv, applies only a unit conversion and rounding, and records
where it came from (file, row selector, column, raw value) in the manifest.
"""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "results" / "stats"
REP = ROOT / "report"
GIB = 1024 ** 3

# --------------------------------------------------------------------------- formatting
def tex_escape(s: str) -> str:
    return re.sub(r"([_&%#$])", r"\\\1", str(s))


def fmt_num(v: float, dec: int, thousands: bool = False) -> str:
    if dec == 0:
        s = f"{round(v):,d}" if thousands else f"{round(v):d}"
    else:
        s = f"{v:,.{dec}f}" if thousands else f"{v:.{dec}f}"
    return s.replace("-", "$-$") if s.startswith("-") else s


# --------------------------------------------------------------------------- sources
TABLES = {name: pd.read_csv(ST / f"{name}.csv") for name in
          ["headline", "setup", "comparison", "scaling", "breakeven", "memory_check", "pca_variance",
           "load_summary", "summary"]}
KV = {name: dict(zip(TABLES[name].key, TABLES[name].value)) for name in ["headline", "setup"]}

# Decimals for headline values (raw values; *_pct keys are value x 100).
HEAD_DEC = {
    "duck_faster_ratio_min": 2, "duck_faster_ratio_max": 2, "ratio_min_q1_q21": 2,
    "cold_ch_faster_ratio_min": 2, "cold_ch_faster_ratio_max": 2,
    "cold_over_warm_min": 1, "cold_over_warm_max": 1, "cold_over_warm_median": 1,
    "cv_max_pct": 0, "slope_min": 2, "slope_max": 2, "slope_median": 2,
    "peak_ratio_min_sf1": 1, "peak_ratio_max_sf1": 1, "peak_ratio_min_sf10": 1, "peak_ratio_max_sf10": 1,
    "idle_gib_clickhouse_sf1": 2, "idle_gib_duckdb_sf1": 2,
    "engine_peak_max_gib_clickhouse_sf10": 2, "engine_peak_max_gib_duckdb_sf10": 2,
    "load_ratio_sf1": 1, "load_ratio_sf10": 1, "disk_ratio_sf1": 2, "disk_ratio_sf10": 2,
    "max_p_holm_significant": 4, "mw_min_p_5v5": 3, "pilot_load_minutes": 0, "pilot_query_minutes": 0,
    "ch_engine_peak_max_gib": 2, "full_study_query_runs": 0, "ch_client_overhead_median_ms": 1, "peak_max_gib": 2,
    "order_share_below_5pct_n10_pct": 0, "order_share_below_5pct_n15_pct": 0, "order_share_below_5pct_n20_pct": 0,
    "mw_min_p_3v3": 2, "h1_n_tests": 0, "h1_n_supported": 0, "h2_n_tests": 0, "h2_n_supported": 0,
    "h3_n_sf_duck_10pct_faster": 0,
    "import_mrows_s_clickhouse_sf1": 1, "import_mrows_s_clickhouse_sf10": 1,
    "import_mrows_s_duckdb_sf1": 1, "import_mrows_s_duckdb_sf10": 1,
    "total_mrows_s_clickhouse_sf1": 1, "total_mrows_s_clickhouse_sf10": 1,
    "total_mrows_s_duckdb_sf1": 1, "total_mrows_s_duckdb_sf10": 1,
    "added_peak_max_gib_clickhouse_sf10": 2, "added_peak_max_gib_duckdb_sf10": 2,
    "order_median_halfwidth_n20_pct": 1, "order_max_halfwidth_n20_pct": 1, "boot_median_halfwidth_n3_pct": 1,
}

MANIFEST: list[dict] = []


def record(key, file, selector, column, raw, shown):
    MANIFEST.append(dict(key=key, file=file, selector=selector, column=column, raw=raw, shown=shown))
    return shown


def cell(table: str, selector: dict, column: str):
    df = TABLES[table]
    m = pd.Series(True, index=df.index)
    for k, v in selector.items():
        m &= df[k] == v
    sub = df[m]
    if len(sub) != 1:
        raise KeyError(f"{table} {selector}: {len(sub)} rows")
    return sub.iloc[0][column]


def resolve(key: str) -> str:
    ns, name = key.split(".", 1)
    if ns == "headline":
        base, scale = (name[:-4], 100) if name.endswith("_pct") and name not in KV["headline"] else (name, 1)
        try:
            raw = float(KV["headline"][base])
        except ValueError:  # text facts such as a list of query names
            return record(key, "headline.csv", f"key={base}", "value", KV["headline"][base], tex_escape(KV["headline"][base]))
        dec = HEAD_DEC.get(name, 0 if base.startswith("n_") else 2)
        return record(key, "headline.csv", f"key={base}", "value", raw, fmt_num(raw * scale, dec))
    if ns == "setup":
        if name.endswith("_parquet_gb"):
            base = name.replace("_gb", "_bytes")
            raw = float(KV["setup"][base])
            return record(key, "setup.csv", f"key={base}", "value", raw, fmt_num(raw / 1e9, 2))
        raw = KV["setup"][name]
        if name.endswith("_rows"):
            return record(key, "setup.csv", f"key={name}", "value", raw, fmt_num(float(raw), 0, thousands=True))
        if name == "host_mem_gib":
            return record(key, "setup.csv", f"key={name}", "value", raw, fmt_num(float(raw), 0))
        return record(key, "setup.csv", f"key={name}", "value", raw, tex_escape(raw))
    if ns == "be":
        sf = int(name[2:])
        raw = cell("breakeven", {"sf": sf, "load_basis": "total_s"}, "n_star")
        return record(key, "breakeven.csv", f"sf={sf},load_basis=total_s", "n_star", raw, fmt_num(raw, 1))
    if ns == "memory":
        col, scale, dec = {"median_interval_ms": ("median_interval_ms", 1, 1), "max_interval_ms": ("max_interval_ms", 1, 1),
                           "share_below_1pct": ("share_gap_below_1pct", 100, 1), "max_gap_pct": ("max_rel_gap", 100, 1)}[name]
        raw = float(TABLES["memory_check"].iloc[0][col])
        return record(key, "memory_check.csv", "row=0", col, raw, fmt_num(raw * scale, dec))
    if ns == "pca":
        comp = name.split("_")[0]
        raw = cell("pca_variance", {"component": comp}, "explained")
        return record(key, "pca_variance.csv", f"component={comp}", "explained", raw, fmt_num(raw * 100, 0))
    if ns.startswith("q") and "sf" in ns:  # e.g. q13sf10.ratio
        q, sf = map(int, re.match(r"q(\d+)sf(\d+)", ns).groups())
        col = {"ratio": "ratio_ch_over_duck", "ratio_lo": "ratio_lo", "ratio_hi": "ratio_hi", "p_holm": "p_holm"}[name]
        raw = cell("comparison", {"sf": sf, "query_id": q}, col)
        return record(key, "comparison.csv", f"sf={sf},query_id={q}", col, raw, fmt_num(raw, 2))
    if ns == "slope":
        eng = {"ch": "clickhouse", "dk": "duckdb"}[name[:2]]
        q = int(name[2:])
        raw = cell("scaling", {"engine": eng, "query_id": q}, "slope_b")
        return record(key, "scaling.csv", f"engine={eng},query_id={q}", "slope_b", raw, fmt_num(raw, 2))
    if ns == "load" and name == "anon_max_sf10":
        df = TABLES["load_summary"]
        raw = float(df[df.sf == 10].load_anon_peak_max_bytes.max())
        return record(key, "load_summary.csv", "sf=10,max over engines", "load_anon_peak_max_bytes", raw,
                      fmt_num(raw / GIB, 2))
    raise KeyError(key)


# --------------------------------------------------------------------------- tables
def ms(v):
    return fmt_num(v, 1 if v < 100 else 0)


def latency_table() -> str:
    c, s = TABLES["comparison"], TABLES["summary"].set_index(["engine", "sf", "query_id"])
    lines = []
    for sf in sorted(c.sf.unique()):
        for _, r in c[c.sf == sf].iterrows():
            q = int(r.query_id)
            ch, dk = s.loc[("clickhouse", sf, q)], s.loc[("duckdb", sf, q)]
            p = "$<$0.001" if r.p_holm < 0.001 else fmt_num(r.p_holm, 2)
            for eng, row in (("clickhouse", ch), ("duckdb", dk)):
                for col in ("warm_median_ms", "ci_lo_ms", "ci_hi_ms"):
                    record(f"T1.{eng}.sf{sf}.q{q}.{col}", "summary.csv", f"engine={eng},sf={sf},query_id={q}", col,
                           row[col], ms(row[col]))
            for col in ("ratio_ch_over_duck", "ratio_lo", "ratio_hi", "p_holm", "cliffs_delta"):
                record(f"T1.sf{sf}.q{q}.{col}", "comparison.csv", f"sf={sf},query_id={q}", col, r[col],
                       p if col == "p_holm" else fmt_num(r[col], 2))
            lines.append(
                f"{sf} & Q{q} & {r.query_class} & {ms(ch.warm_median_ms)} [{ms(ch.ci_lo_ms)}, {ms(ch.ci_hi_ms)}] & "
                f"{ms(dk.warm_median_ms)} [{ms(dk.ci_lo_ms)}, {ms(dk.ci_hi_ms)}] & "
                f"{fmt_num(r.ratio_ch_over_duck, 2)} [{fmt_num(r.ratio_lo, 2)}, {fmt_num(r.ratio_hi, 2)}] & "
                f"{p} & {fmt_num(r.cliffs_delta, 2)} \\\\")
        if sf != c.sf.max():
            lines.append("\\midrule")
    body = "\n".join(lines)
    return rf"""\begin{{table}}[ht]
\centering\footnotesize
\setlength{{\tabcolsep}}{{4.5pt}}
\caption{{Warm latency per query: median of 20 runs [95\,\% bootstrap CI] in ms, ratio of medians \CH/\DK\ [95\,\% CI], Holm-adjusted $p$ of the Mann--Whitney test and Cliff's $\delta$ (negative: \CH\ faster).}}
\label{{tab:latency}}
\begin{{tabular}}{{@{{}}rlllllrr@{{}}}}
\toprule
SF & Query & Class & \CH\ (ms) & \DK\ (ms) & Ratio & $p_\mathrm{{Holm}}$ & $\delta$ \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\end{{table}}
"""


def load_table() -> str:
    d = TABLES["load_summary"]
    lines = []
    for sf in sorted(d.sf.unique()):
        for eng in ("clickhouse", "duckdb"):
            r = d[(d.sf == sf) & (d.engine == eng)].iloc[0]
            vals = {
                "load_median_s": fmt_num(r.load_median_s, 1), "load_min_s": fmt_num(r.load_min_s, 1),
                "load_max_s": fmt_num(r.load_max_s, 1), "finalize_median_s": fmt_num(r.finalize_median_s, 3 if r.finalize_median_s < 0.01 else 2 if r.finalize_median_s < 1 else 1),
                "total_median_s": fmt_num(r.total_median_s, 1), "disk_median_bytes": fmt_num(r.disk_median_bytes / 1e9, 2),
                "disk_over_parquet": fmt_num(r.disk_over_parquet, 2),
                "load_peak_max_bytes": fmt_num(r.load_peak_max_bytes / GIB, 2),
                "load_anon_peak_max_bytes": fmt_num(r.load_anon_peak_max_bytes / GIB, 2),
                "idle_after_restart_median_bytes": fmt_num(r.idle_after_restart_median_bytes / GIB, 2),
            }
            for col, shown in vals.items():
                record(f"T2.{eng}.sf{sf}.{col}", "load_summary.csv", f"engine={eng},sf={sf}", col, r[col], shown)
            name = "\\CH" if eng == "clickhouse" else "\\DK"
            lines.append(f"{name} & {sf} & {vals['load_median_s']} ({vals['load_min_s']}--{vals['load_max_s']}) & "
                         f"{vals['finalize_median_s']} & {vals['total_median_s']} & {vals['disk_median_bytes']} & "
                         f"{vals['disk_over_parquet']} & {vals['load_peak_max_bytes']} / {vals['load_anon_peak_max_bytes']} & "
                         f"{vals['idle_after_restart_median_bytes']} \\\\")
    body = "\n".join(lines)
    return rf"""\begin{{table}}[ht]
\centering\footnotesize
\caption{{Loads (3 per engine and SF). Each column is the median of its own three values, so Total need not equal Import + Merge/ckpt: import time (min--max), merge (\CH) or checkpoint (\DK) time, total; disk footprint and its ratio to the Parquet input (computed from unrounded sizes); peak container / anonymous memory during the load (maximum); container memory right after restart (median over the cold runs). GB = $10^9$ bytes, GiB = $2^{{30}}$ bytes.}}
\label{{tab:load}}
\setlength{{\tabcolsep}}{{4pt}}
\begin{{tabular}}{{@{{}}lrrrrrrrr@{{}}}}
\toprule
Engine & SF & Import (s) & Merge/ckpt (s) & Total (s) & Disk (GB) & Disk/Parquet & Load peak (GiB) & Idle (GiB) \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\end{{table}}
"""


def main():
    tex = (REP / "main.tex").read_text()
    body = re.sub(r"(?m)(?<!\\)%.*$", "", tex)  # ignore comments, keep escaped \%
    keys = sorted(set(re.findall(r"\\V\{([^}]+)\}", body)))
    out = ["% Generated by make_numbers.py from results/stats/*.csv. Do not edit.",
           r"\makeatletter",
           r"\newcommand{\V}[1]{\ifcsname v@#1\endcsname\csname v@#1\endcsname\else\errmessage{Undefined value #1}\fi}"]
    for k in keys:
        out.append(rf"\expandafter\def\csname v@{k}\endcsname{{{resolve(k)}}}")
    out.append(r"\makeatother")
    (REP / "numbers.tex").write_text("\n".join(out) + "\n")
    (REP / "tables").mkdir(exist_ok=True)
    (REP / "tables" / "T1_latency.tex").write_text(latency_table())
    (REP / "tables" / "T2_load.tex").write_text(load_table())
    with (REP / "numbers_manifest.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, ["key", "file", "selector", "column", "raw", "shown"])
        w.writeheader()
        w.writerows(MANIFEST)
    print(f"{len(keys)} macros, {len(MANIFEST)} manifest entries")


if __name__ == "__main__":
    main()
