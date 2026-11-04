# 02 Pin engines and config

Type: task
Status: resolved
Blocked by: 01

## Question

Which exact ClickHouse LTS tag and DuckDB version do we pin, which 8 queries (proposal vs PLAN default), and how is LaTeX compiled? Write config.yaml, docker/ images and Makefile skeleton.

## Answer

Pinned: ClickHouse clickhouse/clickhouse-server:26.8.36.3 (26.8 is the current LTS line; digest in config.yaml). DuckDB 2.0.0 (latest stable on PyPI, released 2026-10-21) in image ii2202/duckdb-bench:2.0.0 built FROM python:3.12-slim@sha256:b18b26..., tpch extension v2.0.0 baked in. Queries follow the Research Plan (it overrides the PLAN default list): scan Q1,Q6; join Q5,Q9,Q21; aggregation Q3,Q13,Q18. Both engine containers: --memory=8g --memory-swap=8g --cpus=4 --cpuset-cpus=0-3; driver on cpus 4-7, privileged, cgroupns=host (to read engine cgroups and drop page cache). ClickHouse: max_server_memory_usage 7 GiB, max_threads 4, external GROUP BY / sort at 3 GiB, query cache and query condition cache off. DuckDB: memory_limit 7GiB, threads 4, temp_directory /tmp/duck_spill. Parquet input lives in docker volume ii2202-parquet (not data/ on the macOS bind mount) because virtiofs reads would add noise to load times. LaTeX: texlive/texlive:latest in Docker (user choice). Attribution: no Claude trailer in commits (standing user rule).

## Comments
