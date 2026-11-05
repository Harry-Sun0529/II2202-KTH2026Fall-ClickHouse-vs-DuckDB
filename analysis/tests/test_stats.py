import sys
from pathlib import Path

import numpy as np
import pytest
from statsmodels.stats.multitest import multipletests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stats as S  # noqa: E402


def test_bootstrap_ci_covers_true_median_at_nominal_rate():
    # Lognormal(mu, sigma) has median exp(mu). 400 experiments of n = 20.
    rng = np.random.default_rng(1)
    true_median = np.exp(3.0)
    hits = 0
    reps = 400
    for i in range(reps):
        x = rng.lognormal(3.0, 0.4, size=20)
        _, lo, hi = S.bootstrap_median_ci(x, B=2000, seed=i)
        hits += lo <= true_median <= hi
    coverage = hits / reps
    # Percentile bootstrap of a median at n = 20 is close to, but not exactly, 95 %.
    assert 0.90 <= coverage <= 0.99, coverage


def test_bootstrap_ci_contains_point_and_is_ordered():
    x = np.array([5.0, 7, 6, 9, 8, 6, 7, 10, 5, 6])
    m, lo, hi = S.bootstrap_median_ci(x)
    assert lo <= m <= hi
    assert m == np.median(x)


def test_fixed_seed_is_reproducible_and_seed_matters():
    x = np.random.default_rng(7).lognormal(0, 1, 30)
    assert S.bootstrap_median_ci(x, seed=3) == S.bootstrap_median_ci(x, seed=3)
    assert S.bootstrap_median_ci(x, seed=3) != S.bootstrap_median_ci(x, seed=4)
    y = x * 1.3
    assert S.break_even_bootstrap([10, 11, 12], [x], [1, 1.5, 2], [y], B=500, seed=5)[1:] == \
        S.break_even_bootstrap([10, 11, 12], [x], [1, 1.5, 2], [y], B=500, seed=5)[1:]


def test_break_even_hand_example():
    # A: load 100 s, 1 s per run. B: load 10 s, 4 s per run.
    # T_A(n) = 100 + n, T_B(n) = 10 + 4n  ->  equal at n* = 90 / 3 = 30.
    r = S.break_even(100, 1, 10, 4)
    assert r.kind == "crossing"
    assert r.n_star == pytest.approx(30)
    assert 100 + 30 * 1 == pytest.approx(10 + 30 * 4)


def test_break_even_dominance_and_parallel():
    # A loads faster AND runs faster: n* = (5 - 10) / (4 - 1) < 0, A always cheaper.
    r = S.break_even(5, 1, 10, 4)
    assert r.kind == "a_always_cheaper" and r.n_star < 0
    r = S.break_even(10, 4, 5, 1)
    assert r.kind == "b_always_cheaper"
    assert S.break_even(5, 2, 10, 2).kind == "a_always_cheaper"
    assert np.isnan(S.break_even(5, 2, 5, 2).n_star)


def test_holm_matches_statsmodels():
    p = np.array([0.01, 0.04, 0.03, 0.005, 0.2, 0.5, 0.001, 0.049])
    ours = S.holm(p)
    ref = multipletests(p, method="holm")[1]
    np.testing.assert_allclose(ours, ref)


def test_cliffs_delta_extremes():
    assert S.cliffs_delta([5, 6, 7], [1, 2, 3]) == 1.0
    assert S.cliffs_delta([1, 2, 3], [5, 6, 7]) == -1.0
    assert S.cliffs_delta([1, 2, 3], [1, 2, 3]) == 0.0
    # hand count: pairs (x>y)=2 [(3,1),(3,2)], (x<y)=2 [(1,2),(1,3)]... over 3x3 = 9
    assert S.cliffs_delta([1, 3, 2], [2, 1, 3]) == pytest.approx(0.0)


def test_mann_whitney_detects_shift():
    rng = np.random.default_rng(0)
    x = rng.normal(10, 1, 20)
    _, p = S.mann_whitney(x, x + 5)
    assert p < 1e-6
    _, p = S.mann_whitney(x, x)
    assert p > 0.9


def test_loglog_slope_exact_linear_scaling():
    x1 = np.array([10.0, 10, 10, 10])
    x10 = x1 * 10
    b, lo, hi = S.loglog_slope(1, x1, 10, x10, B=500)
    assert b == pytest.approx(1.0) and lo == pytest.approx(1.0) and hi == pytest.approx(1.0)
    b, *_ = S.loglog_slope(1, x1, 10, x1 * 100, B=200)
    assert b == pytest.approx(2.0)


def test_order_stat_ci_k_and_coverage():
    # No 95 % order-statistic CI exists for n < 6; n = 6 uses [x(1), x(6)] (coverage 1 - 2/64).
    assert S.order_stat_k(5) is None
    assert S.order_stat_k(6) == 1
    assert S.order_stat_k(20) == 6          # P(Bin(20, .5) <= 5) = 0.0207 <= 0.025
    m, lo, hi, cov = S.median_ci_order_stat(np.arange(1, 21))
    assert (lo, hi) == (6, 15) and cov == pytest.approx(1 - 2 * 0.020694, abs=1e-5)
    assert np.isnan(S.median_ci_order_stat([1, 2, 3])[1])


def test_order_stat_ci_covers_at_least_nominal_bootstrap_undercovers_at_n3():
    rng = np.random.default_rng(11)
    true_median = 1.0  # lognormal(0, s) has median exp(0) = 1
    hit_order, hit_boot3, reps = 0, 0, 2000
    for i in range(reps):
        x = rng.lognormal(0, 0.3, 20)
        _, lo, hi, _ = S.median_ci_order_stat(x)
        hit_order += lo <= true_median <= hi
        _, blo, bhi = S.bootstrap_median_ci(x[:3], B=400, seed=i)
        hit_boot3 += blo <= true_median <= bhi
    assert hit_order / reps >= 0.94          # exact coverage 0.9586
    assert 0.70 <= hit_boot3 / reps <= 0.80  # theory: 1 - 2 (1/2)^3 = 0.75


def test_halfwidth_vs_n_and_min_n():
    x = np.random.default_rng(2).lognormal(0, 0.1, 20)
    w = S.halfwidth_vs_n(x)
    assert set(w) == {3, 5, 10, 15, 20}
    assert np.isnan(w[3]) and np.isnan(w[5]) and w[10] > 0 and w[20] > 0
    # Averaged over many samples the exact CI narrows with n.
    rng = np.random.default_rng(4)
    ws = [S.halfwidth_vs_n(rng.lognormal(0, 0.1, 20)) for _ in range(300)]
    assert np.mean([v[20] for v in ws]) < np.mean([v[10] for v in ws])
    wb = S.halfwidth_vs_n(x, method="bootstrap", B=2000)
    assert all(np.isfinite(v) for v in wb.values())
    assert S.min_n_for({3: np.nan, 5: np.nan, 10: 0.04, 15: 0.03}) == 10
    assert S.min_n_for({3: 0.2, 5: 0.06, 10: 0.04, 15: 0.03}) == 10
    assert np.isnan(S.min_n_for({3: 0.2, 5: 0.1}))


def test_pca_recovers_dominant_direction():
    rng = np.random.default_rng(3)
    t = rng.normal(size=50)
    X = np.c_[t, 2 * t + 0.01 * rng.normal(size=50), rng.normal(size=50)]
    scores, load, ratio = S.pca(X)
    assert ratio[0] > 0.6 and abs(ratio.sum() - 1) < 1e-12
    assert abs(load[0, 0]) == pytest.approx(abs(load[1, 0]), rel=0.01)
