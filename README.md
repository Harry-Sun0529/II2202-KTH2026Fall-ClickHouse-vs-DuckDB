# II2202 Quantitative Exercise — ClickHouse vs DuckDB pilot benchmark

KTH II2202 (Autumn 2026, Period 2), group: Weizhuo Sun, Weiyin Fang.

A pilot of the course project: ClickHouse 26.8 (LTS) and DuckDB 2.0 under one
budget of 8 GiB memory and 4 cores, 8 TPC-H queries, SF1 and SF10. Every number
in the report comes from the CSV files in `results/`.

## Re-run everything

Requirements: Docker Desktop with at least 10 GiB of VM memory and 8 vCPUs,
Python >= 3.12, about 30 GB of free disk. No local TeX installation is needed.

```bash
make all
```

or stage by stage:

| Command | What it does | Output |
|---|---|---|
| `make env` | preflight + gate 0 | `results/env.json` |
| `make image` | build the DuckDB/driver image, pull ClickHouse | — |
| `make data` | TPC-H SF1/SF10 with DuckDB `dbgen`, exported to Parquet (Docker volume `ii2202-parquet`) | `results/data_manifest.json` |
| `make verify` | correctness gate: reference answers at SF1, cross-engine checksums | `results/verification.csv` |
| `make load` | 3 timed loads per engine and SF | `results/load_runs.csv` |
| `make bench` | 1 cold + 20 warm runs per engine × SF × query | `results/raw_runs.csv` |
| `make check` | completeness and sanity gate | `results/stats/gate2.json` |
| `make analyze` | tests, statistics, figures, accessibility renderings | `results/stats/*.csv`, `figures/` |
| `make report` | LaTeX in the `texlive/texlive` container + report gates | `report/II2202_Quantitative_Exercise.pdf` |

## Layout

```
config.yaml           all fixed settings (versions, limits, queries, repetitions, seed)
docker/               ClickHouse config overrides; Dockerfile of the DuckDB/driver image
scripts/              preflight, data generation, verification, load, bench, memory sampler
queries/{clickhouse,duckdb}/qNN.sql   query texts (only one dialect edit, see q13)
results/              env.json, raw_runs.csv, load_runs.csv, verification.csv, stats/
analysis/             stats.py (methods), eda.py (tables), figures.py, tests/
figures/              F1–F6 as PDF + PNG, greyscale and deuteranopia checks in figures/check/
report/               main.tex, numbers.tex (generated), tables/, checklist.md, final PDF
.scratch/ii2202-quant/ wayfinder map and tickets: how the work was split and decided
```

## How the measurement works

Both engines run in their own container with `--memory=8g --memory-swap=8g
--cpus=4 --cpuset-cpus=0-3`. DuckDB is embedded, so its container runs a small
Python server (`scripts/duck_server.py`) that holds the DuckDB connection, the
same way an application would. The driver container (`scripts/bench.py`) runs on
the other four vCPUs, restarts the engines and drops the VM page cache before
each cold run, and samples the engine container's cgroup (`memory.current`,
`memory.stat`) every 2 ms during each query; the kernel's `memory.peak`
watermark is reset before each query and logged as a check.
