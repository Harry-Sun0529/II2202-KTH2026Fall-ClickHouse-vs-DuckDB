"""Statistical methods used in the report (Section 5.3 of the plan).

All functions are pure and take an explicit seed where randomness is involved,
so every number in results/stats/ can be reproduced exactly.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

B_DEFAULT = 10_000
SEED = 20261105


# ----------------------------------------------------------------- descriptive
def bootstrap_median_ci(x, B: int = B_DEFAULT, alpha: float = 0.05, seed: int = SEED):
    """Median and percentile-bootstrap (1 - alpha) CI of the median."""
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(B, x.size))
    meds = np.median(x[idx], axis=1)
    lo, hi = np.quantile(meds, [alpha / 2, 1 - alpha / 2])
    return float(np.median(x)), float(lo), float(hi)


def bootstrap_ratio_ci(x, y, B: int = B_DEFAULT, alpha: float = 0.05, seed: int = SEED):
    """median(x) / median(y) with a percentile-bootstrap CI (x and y resampled independently)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    rng = np.random.default_rng(seed)
    mx = np.median(x[rng.integers(0, x.size, (B, x.size))], axis=1)
    my = np.median(y[rng.integers(0, y.size, (B, y.size))], axis=1)
    lo, hi = np.quantile(mx / my, [alpha / 2, 1 - alpha / 2])
    return float(np.median(x) / np.median(y)), float(lo), float(hi)


def cv(x) -> float:
    x = np.asarray(x, float)
    return float(np.std(x, ddof=1) / np.mean(x)) if x.size > 1 else np.nan


def shapiro_p(x) -> float:
    x = np.asarray(x, float)
    if x.size < 3 or np.ptp(x) == 0:
        return np.nan
    return float(sps.shapiro(x).pvalue)


# ----------------------------------------------------------------- comparison
def mann_whitney(x, y):
    """Two-sided Mann-Whitney U test. Returns (U of x, p)."""
    r = sps.mannwhitneyu(x, y, alternative="two-sided", method="auto")
    return float(r.statistic), float(r.pvalue)


def holm(pvals) -> np.ndarray:
    """Holm-Bonferroni adjusted p-values (step-down, monotone, capped at 1)."""
    p = np.asarray(pvals, float)
    m = p.size
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(1.0, running)
    return adj


def cliffs_delta(x, y) -> float:
    """P(X > Y) - P(X < Y), in [-1, 1]."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    diff = x[:, None] - y[None, :]
    return float((np.sum(diff > 0) - np.sum(diff < 0)) / diff.size)


def cliffs_magnitude(d: float) -> str:
    """Romano et al. (2006) thresholds."""
    a = abs(d)
    return "negligible" if a < 0.147 else "small" if a < 0.33 else "medium" if a < 0.474 else "large"


# ----------------------------------------------------------------- scaling model
def loglog_slope(sf_lo, x_lo, sf_hi, x_hi, B: int = B_DEFAULT, alpha: float = 0.05, seed: int = SEED):
    """Slope b of log(latency) = a + b log(SF) through the two medians.

    With two SF points the line is exact (no residuals), so the CI only carries
    run-to-run noise: both samples are resampled and b recomputed.
    """
    x_lo, x_hi = np.asarray(x_lo, float), np.asarray(x_hi, float)
    d = np.log(sf_hi) - np.log(sf_lo)
    b = (np.log(np.median(x_hi)) - np.log(np.median(x_lo))) / d
    rng = np.random.default_rng(seed)
    m_lo = np.median(x_lo[rng.integers(0, x_lo.size, (B, x_lo.size))], axis=1)
    m_hi = np.median(x_hi[rng.integers(0, x_hi.size, (B, x_hi.size))], axis=1)
    bs = (np.log(m_hi) - np.log(m_lo)) / d
    lo, hi = np.quantile(bs, [alpha / 2, 1 - alpha / 2])
    return float(b), float(lo), float(hi)


# ----------------------------------------------------------------- break-even (RQ3)
@dataclass
class BreakEven:
    n_star: float          # nan when the lines are parallel
    kind: str              # "crossing", "a_always_cheaper", "b_always_cheaper", "parallel"


def break_even(L_a: float, q_a: float, L_b: float, q_b: float) -> BreakEven:
    """Total cost T(n) = L + n q. n* = (L_a - L_b) / (q_b - q_a).

    "crossing": the system with the higher load cost becomes cheaper after n* > 0
    executions. Otherwise one system is cheaper (or equal) for every n >= 0.
    """
    if q_a == q_b:
        if L_a == L_b:
            return BreakEven(np.nan, "parallel")
        return BreakEven(np.nan, "a_always_cheaper" if L_a < L_b else "b_always_cheaper")
    n = (L_a - L_b) / (q_b - q_a)
    if n > 0:
        return BreakEven(float(n), "crossing")
    # n <= 0: no crossing at a positive workload size; the cheaper one at n = 1 wins everywhere.
    return BreakEven(float(n), "a_always_cheaper" if L_a + q_a <= L_b + q_b else "b_always_cheaper")


def break_even_bootstrap(load_a, runs_a: list, load_b, runs_b: list,
                         B: int = B_DEFAULT, alpha: float = 0.05, seed: int = SEED):
    """Bootstrap n*: resample loads and, per query, the warm runs.

    runs_a / runs_b: list (one entry per query) of arrays of warm latencies (s).
    q is the sum over queries of the median warm latency = one run of the query set.
    Returns (point estimate, lo, hi, share of resamples with a crossing).
    """
    rng = np.random.default_rng(seed)

    def q_of(runs, boot):
        if not boot:
            return float(sum(np.median(r) for r in runs))
        return sum(np.median(np.asarray(r)[rng.integers(0, len(r), (B, len(r)))], axis=1) for r in runs)

    la, lb = np.asarray(load_a, float), np.asarray(load_b, float)
    point = break_even(float(np.median(la)), q_of(runs_a, False), float(np.median(lb)), q_of(runs_b, False))
    La = np.median(la[rng.integers(0, la.size, (B, la.size))], axis=1)
    Lb = np.median(lb[rng.integers(0, lb.size, (B, lb.size))], axis=1)
    qa, qb = q_of(runs_a, True), q_of(runs_b, True)
    with np.errstate(divide="ignore", invalid="ignore"):
        n = (La - Lb) / (qb - qa)
    crossing = n > 0
    share = float(np.mean(crossing))
    if share > 0:
        lo, hi = np.quantile(n[crossing], [alpha / 2, 1 - alpha / 2])
    else:
        lo = hi = np.nan
    return point, float(lo), float(hi), share


# ----------------------------------------------------------------- how much data
def relative_halfwidth(x, B: int = B_DEFAULT, alpha: float = 0.05, seed: int = SEED) -> float:
    m, lo, hi = bootstrap_median_ci(x, B, alpha, seed)
    return (hi - lo) / 2 / m


def halfwidth_vs_n(x, ns=(3, 5, 10, 15, 20), B: int = B_DEFAULT, seed: int = SEED) -> dict:
    """Relative CI half-width of the median if only the first n warm runs had been made."""
    x = np.asarray(x, float)
    return {n: relative_halfwidth(x[:n], B=B, seed=seed) for n in ns if n <= x.size}


def min_n_for(widths: dict, target: float = 0.05):
    ok = [n for n, w in sorted(widths.items()) if w < target]
    return ok[0] if ok else np.nan


# ----------------------------------------------------------------- PCA
def pca(X):
    """PCA on the column-standardised matrix X (rows = observations).

    Returns scores, loadings (columns = components), explained variance ratio.
    """
    X = np.asarray(X, float)
    Z = (X - X.mean(axis=0)) / X.std(axis=0, ddof=1)
    U, S, Vt = np.linalg.svd(Z, full_matrices=False)
    scores = U * S
    var = S ** 2 / (Z.shape[0] - 1)
    return scores, Vt.T, var / var.sum()
