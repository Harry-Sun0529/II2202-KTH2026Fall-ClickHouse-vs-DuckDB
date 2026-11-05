# Map: II2202 Quantitative Exercise (ClickHouse vs DuckDB pilot)

Label: wayfinder:map

## Destination

A submittable `report/II2202_Quantitative_Exercise.pdf` built from real pilot
measurements (ClickHouse vs DuckDB, 8 TPC-H queries, SF1 + SF10, 8 GiB / 4 cores),
plus a repository that re-runs the whole pipeline with `make all`.

## Notes

- Source of truth for the task: `II2202_quantitative_exercise_PLAN.md` (user, 2026-11-04).
  Where it says "follow the proposal", the Research Plan (2026-10-07) wins.
- **Execution override**: the user asked to implement every ticket locally, so tickets
  here include doing the work, not only deciding. One git commit per resolved ticket.
- Each ticket has a verification gate; a ticket is resolved only when its gate passes.
- Integrity: every number in the report comes from a real run. Failures are results.
- Tracker: local markdown (`.scratch/ii2202-quant/issues/NN-*.md`).

## Decisions so far

- [01 Preflight and gate 0](issues/01-preflight.md) — Docker VM raised to 10240 MiB by user; M1 Pro 8 cores; full SF1+SF10 at 8 GiB/4 cores, no fallback needed.
- [02 Pin engines and config](issues/02-pin-engines-config.md) — ClickHouse 26.8.36.3 (LTS), DuckDB 2.0.0; Q1,Q6 / Q5,Q9,Q21 / Q3,Q13,Q18 from the Research Plan; LaTeX via Docker texlive.
- [03 Generate TPC-H Parquet](issues/03-generate-data.md) — dbgen SF1/SF10 to Parquet in a Docker volume; all row counts match the spec.
- [04 Queries and correctness gate](issues/04-queries-correctness.md) — all 8 queries run unchanged on both engines except Q13 on ClickHouse (join_use_nulls = 1); both engines match the reference at SF1 and each other at SF10.
- [05 Measurement harness](issues/05-harness.md) — cgroup sampling at ~3 ms for both engines, checked against memory.peak; failures recorded and recovered.
- [06 Full pilot campaign](issues/06-campaign.md) — 672 runs + 12 loads, 0 errors, all results correct; peaks <= 4.89 GiB for queries, so no spill thresholds were tested.
- [07 Statistics module and tests](issues/07-stats.md) — 13 tests pass; bootstrap CIs under-cover at n < 6, so the repetition analysis uses exact order-statistic CIs.
- [08 EDA and figures](issues/08-eda-figures.md) — 14 stats tables and F1-F6, checked at 300 dpi, greyscale and deuteranopia; one silently dropped PCA arrow fixed.

## Not yet specified

- Wording of the report's results and discussion (ticket 09).

## Out of scope

- Part 1 quiz and Part 3 peer review (individual, must be done by the students).
- Concurrency experiments (only proposed for the full study).
- Canvas submission (done by a student after Weiyin's review).
