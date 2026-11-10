# Checklist: II2202 Quantitative Exercise (Part 2, group report)

Report: `report/II2202_Quantitative_Exercise.pdf` (9 pages). Checked 2026-11-05, re-checked 2026-11-10.

**2026-11-07, branch `report-plan-alignment`:** 'Research plan' paragraph and Table 5 (deviations from the plan) at the end of §5, H1–H3 judged with the plan's rules, the plan's peak-minus-baseline metric, ethics and sustainability in §8, load throughput, source of the reference answers, aborted load campaign; light humanizer pass on the prose. No AI-use statement (group decision). The PDF now has 9 pages. It was built on Windows with Tectonic 0.17 (XeTeX) and the Source Sans 3.052 OTF files, because Docker was not available; Gate 4 passed on that build. `make report` (LuaLaTeX in texlive) gives the same text, but the line breaks can differ slightly. The PDF in the repo is still the old build: run `make report` before you submit.

**2026-11-10, final check before submission:** rebuilt with `make report` (LuaLaTeX, TeX Live 2026 in Docker); Gate 4 passed (9 pages, 450 number tokens all traced, no overfull boxes). Three rows of the deviations table (Table 5) were corrected against the research plan PDF (2026-10-07): the plan sets the same 8 GiB limit for both engines through the cgroup, records the time until background merges finish (no '30 s' rule), and its sensitivity check reruns SF10 queries with explicit ClickHouse spill thresholds (not `grace_hash`). 'close to zero for warm runs' → 'for most warm runs' (the largest median is 1.10 GiB). Header date set to November 10, 2026. Analysis tests 13/13 and Gate 2 re-run: pass.

## Step 1 (analysis in Python)

| Requirement | Status | Where |
|---|---|---|
| Pre-process and load data into an analysis tool (Python) | ✅ | `scripts/` produce CSVs; `analysis/eda.py` (pandas); report §4 Preprocessing |
| Load data | ✅ | `results/raw_runs.csv` (672 rows), `results/load_runs.csv` (12 rows) |
| Independent vs dependent variables, with expected properties | ✅ | report §3, Table 2, E1–E8 (taken from PLAN §5.1, written before the analysis) |
| EDA: does the data match expectations? reasons if not | ✅ | report §5 (each E checked; E3, E5, E7, E8 not or partly met, with reasons/hypotheses) |
| Statistical method; fit a model, or explain how to find one (PCA) | ✅ | report §4 items 1–6; scaling model fitted (§5 Scaling); PCA (§5, Figure 6) |
| Graphs | ✅ | `figures/F1–F6` (vector PDF), Tables 3–4 generated from CSVs |

## Step 2 (report)

| Requirement | Status | Where |
|---|---|---|
| Figures checked when enlarged; no loss of clarity | ✅ | vector PDFs; 300 dpi PNGs inspected; printed scale ≈ 1:1 (fonts ≥ 7 pt) |
| Colours readable for colour-blind readers and in greyscale | ✅ | Okabe–Ito + hatching/markers/line styles; `figures/check/*_gray.png`, `*_deuteranopia.png` inspected |
| (a) Dataset description | ✅ | §2, Table 1 |
| (b) Variables and initial expected properties | ✅ | §3, Table 2, E1–E8 |
| (c) Data analysis process | ✅ | §4 |
| (d) Results with figures/tables referenced and explained in words | ✅ | §5: Figures 1–6, Tables 3–4 all referenced and explained |
| (e) Discussion ≥ 100 words: expectations met/different? most useful data? more data? generality and accuracy? | ✅ | §7, 265 words (source count by `check_report.py`); all four questions answered |
| Section on what data, and how much, the group must collect | ✅ | §6 + Table 6 (repetitions, cold runs, loads, scale factors, memory pressure, concurrency, configuration, machine, total runs) |

| Deviations from the research plan listed, H1–H3 evaluated with the plan's rules | ✅ | §5 'Research plan' paragraph + Table 5; H1 0/10, H2 0/3, H3 direction only (3 loads, min p 0.10) |
| Ethics and sustainability | ✅ | §8 (Reproducibility, ethics and sustainability) |

## Gate 4 (automatic, `make report`)

- LaTeX: 0 errors, no undefined references or citations, no overfull box > 10 pt, no `??`.
- Discussion: 265 words (≥ 100; plan target 200–300).
- Figure 5: background lines grey, only the two medians coloured.
- Numbers: 296 manifest entries all equal the current `results/stats/*.csv`; 423 number tokens in the expanded report: 279 matched to a CSV value, 144 are design constants listed with a reason in `check_report.py`; `main.tex` contains no hand-typed data values. Negative tests (injected wrong numbers, stale manifest value) are detected.
- PDFs are byte-reproducible (`SOURCE_DATE_EPOCH`, no figure timestamps).

## Independent review (fresh subagent, assignment text + PDF only) and outcome

| # | Severity | Finding | Outcome |
|---|---|---|---|
| 1 | must-fix | "At SF1 the cold runs ranked the engines as the warm runs did" contradicts Figure 1 | **Fixed.** Verified in data: rank flips are Q13 (SF1) and Q6, Q3, Q18 (SF10); text now generated from `headline.csv` |
| 2 | should | Table 4 Total ≠ Import + Merge | Fixed: caption says every column is its own median |
| 3 | should | "highest peak of any run" ignores 8 GiB load peaks; no-spill inferred from 7 GiB although ClickHouse spills at 3 GiB | Fixed: "query run"; no-spill now based on the recorded spill counters (0 runs) |
| 4 | should | "DuckDB needed much less" holds only at container level | Fixed: "DuckDB's container", engine-own numbers already given |
| 5 | should | Item 5 "because" clause explained the wrong thing | Fixed (reworded) |
| 6 | should | p-values only reflect run-to-run noise; text "≤ 0.0001" vs table "< 0.001" | Fixed: caveat added; both use "< 0.001" |
| 7 | should | "emptied page cache" while macOS cache was not emptied | Fixed in Procedure and Latency paragraph |
| 8 | should | No reason for the E5 mismatch in §5 | Fixed: hedged candidate causes, marked as untested |
| 9 | should | Same star for both engines' cold runs | Fixed; later Figure 1 was redesigned (SF1/SF10 stacked full width, no jittered points, cold run = engine-coloured diamond above its box) |
| 10 | should | Figure 2 fonts ~5 pt, pale Q18, hidden slope line | Fixed: full width ~1:1, Q18 dark grey, dashed slope-1 line on top, legend replaced by end labels with each query's slope b |
| 11 | should | Table 5 not quantified | Fixed: stopping rule (5 %, max 40), SF30 / 4 GiB, Mann–Whitney min p 0.008, total 1344 runs, pilot durations |
| 12 | minor | 3.0 vs 9.8/3.2 = 3.06 | No change: 3.0 is correct from unrounded medians (9.77/3.25) |
| 13 | minor | Disk/Parquet looks off from rounded values; GB vs GiB | Caption: ratios from unrounded sizes; GB/GiB defined |
| 14 | minor | A and B undefined; −21.6 vs −22.0 | A/B defined; −21.6 is correct from unrounded values |
| 15 | minor | "E4 holds" while most CIs exclude 1 | "consistent with E4"; sentence reworded |
| 16 | minor | "E7 therefore holds" | "E7 holds in part" |
| 17 | minor | "a few slow outliers" not true everywhere | "In most combinations" |
| 18 | minor | Q5/Q9 "opposite ends"; small sample | "opposite sides"; "with only eight queries this is a weak test" |
| 19 | minor | cpuset, one engine at a time, Docker version | All three stated (cpuset 0-3; one engine container at a time during measurements; Docker Engine 29.0.1) |
| 20 | minor | Which latency Table 3 reports for ClickHouse | Stated in §2 Procedure |
| 21 | minor | Figure 3 caption and invisible DuckDB idle dash; labels on lines | Caption fixed; labels moved off the lines |
| 22 | minor | Figure 4 markers at fractional n; equation format | Markers at n = 0, 10, …; "9.8 s + 0.65 s · n" |
| 23 | minor | Figure 6 label collisions and contrast | Labels moved, darker and larger |
| 24 | minor | Disk is RQ2, not RQ1 | Split into its own sentence |
| 25 | minor | Reference to the qualitative exercise unexplained | Explained in Table 5 |
| 26 | minor | Wording ("reached", "small samples") | Fixed |
| A | — | Analysis tool never named | Fixed: Python (pandas, SciPy, statsmodels, matplotlib) |

Not changed on purpose: page count. The plan's target was 4–6 pages; the report has 9 (8 before the research-plan table) because of six figures, five tables and the review fixes. The assignment itself sets no length.

## Still for the students

- [ ] Weiyin reviews the PDF (and may change the header date, `\reportdate` in `report/main.tex`).
- [ ] One of you submits on Canvas (course 63857, assignment 393683) before 2026-11-13 19:00.
- [ ] Part 1 quiz (each student).
- [ ] Part 3 peer review (each student, within two working days after the deadline).

## Peer-review checklist (Part 3, for reading another group's report)

1. (a) Is the dataset described well enough to repeat: source, size, how it was collected or generated, units?
2. (b) Are independent and dependent variables named, typed, and given *expected* properties before the results?
3. (c) Is the analysis process clear: preprocessing, cleaning (and what was removed), the statistical methods and why they fit the data (e.g. medians/nonparametric tests for skewed data)?
4. (d) Is every figure and table referenced in the text, and does the text say what the reader should see? Are axes labelled with units? Do the numbers in the text agree with the figures/tables?
5. Figures: readable at print size? usable in greyscale and for colour-blind readers?
6. (e) Discussion ≥ 100 words, and does it answer all four questions (expectations vs results, most useful data, would more data help, generality/accuracy)?
7. "How much data": do they say concretely how many repetitions/samples and which conditions the real study needs, and justify it from the pilot (e.g. CI width vs n)?
8. Are conclusions proportional to the evidence (pilot size, one machine/site, few conditions)? Are failures or surprises reported honestly?
9. Is a model fitted, or is a way to find one (e.g. PCA) explained and interpreted?
10. One concrete, kind suggestion that would most improve their report.
