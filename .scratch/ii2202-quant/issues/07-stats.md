# 07 Statistics module and tests

Type: task
Status: resolved
Blocked by: 06

## Question

Implement analysis/stats.py (bootstrap median CI, Mann-Whitney + Holm, Cliff's delta, log-log slope, break-even n*, subsampling CI width, PCA). Gate: pytest covers CI coverage on a known distribution, n* on a hand example, seed reproducibility.

## Answer

analysis/stats.py: percentile bootstrap CI of the median (B = 10,000, seed 20261105), bootstrap CI of the median ratio, Mann-Whitney U (two-sided) with Holm within each SF (8 tests), Cliff's delta with Romano thresholds, log-log slope b through two SF points with a bootstrap CI that carries only run noise (no residuals with 2 points), break-even n* = (L_a - L_b)/(q_b - q_a) with dominance handling and bootstrap, PCA via SVD on standardised columns. Gate passed: 13 pytest tests (bootstrap coverage on lognormal 0.90-0.99, n* = 30 on a hand example, dominance cases, Holm equals statsmodels, Cliff's delta extremes, slope exactly 1 and 2, PCA direction, fixed-seed reproducibility). Decision found while testing: the plan's 'how much data' analysis with bootstrap CIs at n = 3, 5 is invalid - at n = 3 the bootstrap interval is the sample range and covers the true median only 75 % of the time (confirmed by a test), so it looks deceptively narrow. Added the exact distribution-free order-statistic CI (Le Boudec / Hoefler-Belli): no 95 % CI exists for n < 6; coverage >= 95 % confirmed by test. The repetition analysis uses the exact CI; bootstrap is shown for contrast.

## Comments
