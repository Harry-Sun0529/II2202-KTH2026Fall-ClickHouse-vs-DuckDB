# 08 EDA and figures

Type: task
Status: resolved
Blocked by: 07

## Question

Produce results/stats/*.csv and figures F1-F6, T1-T2 with Okabe-Ito colours and markers. Gate: every figure inspected at 300 dpi, in greyscale and with deuteranopia simulation.

## Answer

analysis/eda.py writes 14 tables to results/stats/ (summary, comparison, scaling, load_summary, breakeven, repetitions*, pca_*, memory_check, expectations, setup). analysis/figures.py writes F1-F6 (PDF + 300 dpi PNG); analysis/check_figures.py writes greyscale and deuteranopia renderings (figures/check/, plus figures/*_gray.png). Every figure inspected at 300 dpi, in greyscale and with deuteranopia: engines differ by colour (Okabe-Ito orange vs blue; luminance 0.64 vs 0.34), hatching and marker; queries in F2 by colour, marker and line style. Fixes made during inspection: plain-number log ticks; F4 legends moved below panels (overlapped lines); F5 legend moved out; F6 legend moved out and - a real bug - one PCA loading arrow (ClickHouse SF1 memory) was silently dropped by matplotlib because its tip lay outside the axes; limits now include all arrow tips. Headline: DuckDB faster in 13 of 16 query x SF comparisons; ClickHouse faster on Q13 (both SF, significant) and Q18 at SF10 (not significant after Holm); DuckDB loads faster and is cheaper for every n (no break-even); ClickHouse uses more memory and more disk.

## Comments
