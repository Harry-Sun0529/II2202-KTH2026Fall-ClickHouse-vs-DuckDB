"""Stage 3: figures F1-F6 as vector PDFs (plus 300 dpi PNGs for inspection).

Colour scheme: Okabe-Ito. Every series is also told apart by marker shape,
line style or hatching, so the figures work in greyscale and for colour-blind
readers. figures/check/ gets greyscale and deuteranopia renderings (check_figures.py).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402
from matplotlib.transforms import ScaledTranslation  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ST = ROOT / "results" / "stats"
FIG = ROOT / "figures"
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
QORDER = [q["id"] for q in CFG["queries"]]
QCLASS = {q["id"]: q["class"] for q in CFG["queries"]}
SFS = CFG["data"]["scale_factors"]
GIB = 1024 ** 3

OI = {"orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442",
      "blue": "#0072B2", "vermillion": "#D55E00", "purple": "#CC79A7", "black": "#000000"}
ENG = {  # colour, marker, hatch, label
    "clickhouse": dict(color=OI["orange"], marker="o", hatch="////", label="ClickHouse 26.8"),
    "duckdb": dict(color=OI["blue"], marker="s", hatch="", label="DuckDB 2.0"),
}
QSTYLE = {  # per query: colour, marker, line style (8 Okabe-Ito colours incl. black)
    1: (OI["black"], "o", "-"), 6: (OI["orange"], "s", "--"), 5: (OI["sky"], "^", "-."),
    9: (OI["green"], "v", ":"), 21: (OI["blue"], "D", "-"), 3: (OI["vermillion"], "P", "--"),
    13: (OI["purple"], "X", "-."), 18: ("#555555", "*", ":"),
}
CLASS_LABEL = {"scan": "scan", "join": "join", "aggregation": "aggregation"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "axes.titlesize": 9, "axes.labelsize": 8.5,
    "legend.fontsize": 7.5, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "pdf.fonttype": 42,
    "axes.spines.top": False, "axes.spines.right": False, "hatch.linewidth": 0.6,
})
W = 6.3  # inches, text width of the report


def plain_log_y(ax, subs=(1.0, 2.0, 5.0)):
    """Log axis labelled with plain numbers (20, 50, 100, ...) instead of 2 x 10^1."""
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=subs))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())


def save(fig, name):
    FIG.mkdir(exist_ok=True)
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", metadata={"CreationDate": None})  # reproducible bytes
    fig.savefig(FIG / f"{name}.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def runs():
    r = pd.read_csv(ROOT / "results/raw_runs.csv", keep_default_na=False)
    r["latency_ms"] = pd.to_numeric(r.latency_ms, errors="coerce")
    r["ok"] = (r.error == "") & (r.result_ok.astype(str) == "True")
    return r


def qlabel(q):
    return f"Q{q}"


def class_spans(ax, y=None):
    """Class names under the query labels, at a fixed distance in points below the axis."""
    start = 0
    trans = ax.get_xaxis_transform() + ScaledTranslation(0, -15 / 72, ax.figure.dpi_scale_trans)
    for cls in ["scan", "join", "aggregation"]:
        n = sum(1 for q in QORDER if QCLASS[q] == cls)
        ax.text(start + (n - 1) / 2, 0, CLASS_LABEL[cls], ha="center", va="top",
                transform=trans, fontsize=7.5, style="italic")
        if start:
            ax.axvline(start - 0.5, color="0.75", lw=0.6, zorder=0)
        start += n


def f1_latency(r):
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 2.45), sharey=False)
    rng = np.random.default_rng(0)
    for ax, sf in zip(axes, SFS):
        for k, e in enumerate(["clickhouse", "duckdb"]):
            st = ENG[e]
            pos = np.arange(len(QORDER)) + (k - 0.5) * 0.38
            data = [r[(r.engine == e) & (r.sf == sf) & (r.query_id == q) & (r.phase == "warm") & r.ok].latency_ms
                    for q in QORDER]
            bp = ax.boxplot(data, positions=pos, widths=0.32, patch_artist=True, showfliers=False,
                            medianprops=dict(color="black", lw=1.1), whiskerprops=dict(lw=0.7),
                            capprops=dict(lw=0.7), boxprops=dict(lw=0.7))
            for b in bp["boxes"]:
                b.set_facecolor(st["color"]); b.set_alpha(0.55); b.set_hatch(st["hatch"]); b.set_edgecolor("black")
            for p, d in zip(pos, data):
                ax.scatter(p + rng.uniform(-0.09, 0.09, len(d)), d, s=4, marker=st["marker"],
                           facecolor="none" if e == "clickhouse" else st["color"], edgecolor=st["color"],
                           lw=0.5, zorder=3)
            cold = [r[(r.engine == e) & (r.sf == sf) & (r.query_id == q) & (r.phase == "cold") & r.ok].latency_ms for q in QORDER]
            for p, c in zip(pos, cold):
                if len(c):
                    ax.scatter([p], c, marker="*", s=55, zorder=4, linewidths=0.8, edgecolors="black",
                               facecolors="white" if e == "clickhouse" else "black")
        ax.set_yscale("log")
        plain_log_y(ax)
        ax.set_xticks(range(len(QORDER)), [qlabel(q) for q in QORDER])
        ax.set_title(f"SF{sf}")
        ax.set_ylabel("Query latency (ms, log scale)" if sf == SFS[0] else "")
        class_spans(ax, -0.09)
        ax.grid(axis="y", which="major", color="0.88", lw=0.5)
    handles = [Patch(facecolor=ENG[e]["color"], alpha=0.55, hatch=ENG[e]["hatch"], edgecolor="black",
                     label=ENG[e]["label"] + " (20 warm runs)") for e in ENG]
    handles.append(Line2D([], [], marker="*", mfc="white", mec="black", lw=0, markersize=9, label="ClickHouse cold run"))
    handles.append(Line2D([], [], marker="*", mfc="black", mec="black", lw=0, markersize=9, label="DuckDB cold run"))
    fig.legend(handles=handles, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.13), frameon=False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "F1_latency")


def f2_scaling():
    s = pd.read_csv(ST / "summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(4.5, 2.3), sharey=True)
    for ax, e in zip(axes, ["clickhouse", "duckdb"]):
        for q in QORDER:
            c, m, ls = QSTYLE[q]
            d = s[(s.engine == e) & (s.query_id == q)].sort_values("sf")
            ax.plot(d.sf, d.warm_median_ms, color=c, marker=m, ls=ls, lw=1.3, ms=5.5, mec=c, mew=0.5, label=qlabel(q))
        x = np.array(SFS, float)
        y0 = s[s.engine == e].groupby("sf").warm_median_ms.median().loc[SFS[0]]
        ax.plot(x, y0 * x / x[0], color="black", lw=0.9, ls=(0, (6, 3)), zorder=5, label="slope 1 (linear)")
        ax.set_xscale("log"); ax.set_yscale("log")
        plain_log_y(ax)
        ax.set_xticks(SFS, [f"SF{v}" for v in SFS])
        ax.minorticks_off()
        ax.set_xlim(0.8, 12.5)
        ax.set_title(ENG[e]["label"])
        ax.set_xlabel("Scale factor (log scale)")
        ax.grid(color="0.9", lw=0.5)
    axes[0].set_ylabel("Median warm latency (ms, log scale)")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
    fig.tight_layout()
    save(fig, "F2_scaling")


def f3_memory():
    s = pd.read_csv(ST / "summary.csv")
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 2.35), sharey=True)
    for ax, sf in zip(axes, SFS):
        for k, e in enumerate(["clickhouse", "duckdb"]):
            st = ENG[e]
            d = s[(s.engine == e) & (s.sf == sf)].set_index("query_id").loc[QORDER]
            pos = np.arange(len(QORDER)) + (k - 0.5) * 0.4
            ax.bar(pos, d.peak_median_bytes / GIB, width=0.38, color=st["color"], alpha=0.75,
                   hatch=st["hatch"], edgecolor="black", lw=0.6, label=st["label"] + ": median peak")
            ax.errorbar(pos, d.peak_median_bytes / GIB,
                        yerr=[np.zeros(len(d)), (d.peak_max_bytes - d.peak_median_bytes) / GIB],
                        fmt="none", ecolor="black", elinewidth=0.7, capsize=2)
            ax.scatter(pos, d.baseline_cold_bytes / GIB, marker="_", s=60, color="black", lw=1.4, zorder=4,
                       label="idle after restart" if k == 0 else None)
        ax.axhline(7, color="black", ls="--", lw=0.9)
        ax.axhline(8, color="black", ls=":", lw=1.1)
        ax.text(len(QORDER) - 0.45, 7.08, "engine limit 7 GiB", ha="right", va="bottom", fontsize=7)
        ax.text(len(QORDER) - 0.45, 8.08, "container limit 8 GiB", ha="right", va="bottom", fontsize=7)
        ax.set_xticks(range(len(QORDER)), [qlabel(q) for q in QORDER])
        ax.set_ylim(0, 8.8)
        ax.set_title(f"SF{sf}")
        class_spans(ax, -0.09)
        ax.grid(axis="y", color="0.9", lw=0.5)
    axes[0].set_ylabel("Container memory peak (GiB)")
    h, l = axes[0].get_legend_handles_labels()
    h.append(Line2D([], [], color="black", lw=0.7, marker="|", markersize=6, label="max over 21 runs"))
    fig.legend(handles=h, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.13), frameon=False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, "F3_memory")


def f4_breakeven():
    be = pd.read_csv(ST / "breakeven.csv")
    be = be[be.load_basis == "total_s"]
    fig, axes = plt.subplots(1, 2, figsize=(5.05, 2.4))
    for ax, sf in zip(axes, SFS):
        row = be[be.sf == sf].iloc[0]
        nmax = max(10.0, 2.2 * row.n_star) if row.kind == "crossing" else 50.0
        n = np.arange(0, int(nmax) + 1)
        for e, L, q, ls in [("clickhouse", row.L_ch_s, row.q_ch_s, "-"), ("duckdb", row.L_duck_s, row.q_duck_s, "--")]:
            st = ENG[e]
            ax.plot(n, L + n * q, color=st["color"], ls=ls, lw=1.6, marker=st["marker"], ms=4, markevery=10,
                    label=f"{st['label']}: T(n) = {L:.1f} s + {q:.2f} s $\\cdot$ n")
        if row.kind == "crossing":
            y = row.L_ch_s + row.n_star * row.q_ch_s
            ax.axvline(row.n_star, color="black", lw=0.8, ls=":")
            ax.annotate(f"n* = {row.n_star:.1f}", (row.n_star, y), xytext=(8, -18), textcoords="offset points", fontsize=7.5)
        else:
            who = "ClickHouse" if row.kind.startswith("clickhouse") else "DuckDB"
            ax.text(0.03, 0.97, f"no crossing for n > 0:\n{who} cheaper\nfor every n",
                    transform=ax.transAxes, va="top", ha="left", fontsize=7)
        ax.set_xlabel("Executions n of the 8-query set")
        ax.set_title(f"SF{sf}")
        ax.set_xlim(0, nmax); ax.set_ylim(bottom=0)
        ax.grid(color="0.9", lw=0.5)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.27), frameon=False, fontsize=6.8)
    axes[0].set_ylabel("Total time T(n) (s)")
    fig.tight_layout()
    save(fig, "F4_breakeven")


def f5_repetitions():
    allm = pd.read_csv(ST / "repetitions.csv")
    d = allm[allm.method == "order"].dropna(subset=["rel_halfwidth"])
    boot = allm[allm.method == "bootstrap"]
    fig, ax = plt.subplots(figsize=(2.85, 3.05))
    for (e, sf, q), b in d.groupby(["engine", "sf", "query_id"]):
        ax.plot(b.n, 100 * b.rel_halfwidth, color=ENG[e]["color"], lw=0.5, alpha=0.35, ls="-" if e == "clickhouse" else "--")
    for k, e in enumerate(["clickhouse", "duckdb"]):
        g = d[d.engine == e].groupby("n").rel_halfwidth.median() * 100
        ax.plot(g.index, g.values, color=ENG[e]["color"], marker=ENG[e]["marker"], lw=2, ls="-" if e == "clickhouse" else "--",
                mfc="white" if e == "clickhouse" else ENG[e]["color"], label=ENG[e]["label"] + ": exact CI,\nmedian of 16")
    gb = boot.groupby("n").rel_halfwidth.median() * 100
    ax.plot(gb.index, gb.values, color="0.35", lw=1, ls=(0, (1, 1)), marker="x", ms=4,
            label="bootstrap CI, median of 32\n(under-covers for n < 6)")
    ax.axvspan(2.5, 5.5, color="0.92", zorder=0)
    ax.text(4, 0.97, "n < 6:\nno exact\nCI", transform=ax.get_xaxis_transform(), ha="center", va="top", fontsize=6.3)
    ax.axhline(5, color="black", ls=":", lw=1)
    ax.text(4, 4.6, "5 %", ha="center", va="top", fontsize=7)
    ax.set_yscale("log")
    plain_log_y(ax)
    ax.set_xticks([3, 5, 6, 10, 15, 20])
    ax.set_xlabel("Warm runs n (first n of 20)")
    ax.set_ylabel("Relative half-width of the\n95 % CI of the median (%)")
    ax.grid(color="0.9", lw=0.5)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.45, -0.2), fontsize=6.5, ncol=1)
    fig.tight_layout()
    save(fig, "F5_repetitions")


def f6_pca():
    sc = pd.read_csv(ST / "pca_scores.csv")
    ld = pd.read_csv(ST / "pca_loadings.csv")
    var = pd.read_csv(ST / "pca_variance.csv")
    fig, ax = plt.subplots(figsize=(3.3, 3.05))
    cls_style = {"scan": (OI["orange"], "s"), "join": (OI["blue"], "^"), "aggregation": (OI["green"], "o")}
    for cls, (c, m) in cls_style.items():
        d = sc[sc.query_class == cls]
        ax.scatter(d.pc1, d.pc2, color=c, marker=m, s=45, edgecolor="black", lw=0.6, label=cls, zorder=3)
        for _, r in d.iterrows():
            off = {3: (-4, 5), 5: (5, -9), 13: (6, -9)}.get(int(r.query_id), (4, 3))
            ax.annotate(f"Q{r.query_id}", (r.pc1, r.pc2), xytext=off, textcoords="offset points", fontsize=7.5,
                        ha="right" if off[0] < 0 else "left")
    scale = 0.8 * np.abs(sc[["pc1", "pc2"]]).to_numpy().max()
    groups = {}
    for _, r in ld.iterrows():
        kind, e, sf = r.feature.split("_")
        ax.annotate("", xy=(r.pc1 * scale, r.pc2 * scale), xytext=(0, 0), annotation_clip=False,
                    arrowprops=dict(arrowstyle="->", color="0.45" if kind == "lat" else "0.15", lw=0.7,
                                    ls="-" if kind == "lat" else "--"))
        key = ("latency " + ("ClickHouse" if e == "clickhouse" else "DuckDB")) if kind == "lat" else "peak memory"
        groups.setdefault(key, []).append((r.pc1 * scale, r.pc2 * scale))
    for key, pts in groups.items():
        x, y = max(pts, key=lambda p: abs(p[1])) if key != "latency DuckDB" else np.mean(pts, axis=0)
        off, ha = {"peak memory": ((6, -2), "left"), "latency DuckDB": ((-4, -10), "right"),
                   "latency ClickHouse": ((0, -11), "center")}[key]
        ax.annotate(key, (x, y), xytext=off, textcoords="offset points",
                    ha=ha, fontsize=7, color="0.1", style="italic")
    # Axis limits must include every arrow tip, or matplotlib silently drops that arrow.
    allx = np.r_[sc.pc1, ld.pc1 * scale]; ally = np.r_[sc.pc2, ld.pc2 * scale]
    padx, pady = 0.12 * np.ptp(allx), 0.12 * np.ptp(ally)
    ax.set_xlim(allx.min() - padx, allx.max() + padx); ax.set_ylim(ally.min() - pady, ally.max() + pady)
    ax.axhline(0, color="0.85", lw=0.5); ax.axvline(0, color="0.85", lw=0.5)
    ax.set_xlabel(f"PC1 ({100 * var.explained[0]:.0f} % of variance)")
    ax.set_ylabel(f"PC2 ({100 * var.explained[1]:.0f} %)")
    h, l = ax.get_legend_handles_labels()
    h += [Line2D([], [], color="0.45", lw=0.8, label="loading: log latency"),
          Line2D([], [], color="0.15", lw=0.8, ls="--", label="loading: log peak memory")]
    ax.legend(handles=h, frameon=False, fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)
    fig.tight_layout()
    save(fig, "F6_pca")


def main():
    r = runs()
    f1_latency(r)
    f2_scaling()
    f3_memory()
    f4_breakeven()
    f5_repetitions()
    f6_pca()
    print("figures written to", FIG)


if __name__ == "__main__":
    main()
