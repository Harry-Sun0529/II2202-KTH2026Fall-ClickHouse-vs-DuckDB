# 05 Measurement harness

Type: task
Status: resolved
Blocked by: 04

## Question

Build load.py, bench.py and the cgroup memory sampler so that each run writes one row with the plan's columns. Gate: a smoke run (1 query, 1 cold + 2 warm, both engines, SF1) yields plausible rows and the sampler agrees with memory.peak.

## Answer

Harness: scripts/bench.py (queries), scripts/load.py (loads), CgroupSampler in scripts/common.py, scripts/duck_server.py (embedded DuckDB in its own 8 GiB/4-core container). Latency: ClickHouse = client wall time over HTTP on the Docker network (server-side query_duration_ms logged too); DuckDB = in-process execute+fetchall. Peak memory (main metric) = max of cgroup memory.current sampled every 2 ms (achieved ~3 ms) by the driver for both engines; also logged: kernel memory.peak watermark (reset per query; agrees with the sampled max within 0.13% in the smoke test), anon peak from memory.stat, baseline before the query, engine's own number (ClickHouse query_log.memory_usage, DuckDB psutil RSS), spill bytes (ClickHouse ProfileEvents ExternalProcessingCompressedBytesTotal, DuckDB temp-dir peak). Gate passed: SF1 smoke run (Q1, Q9; 1 cold + 2 warm; both engines) gave correct checksums and plausible values; killing either container mid-query records the error with OOMKilled/exit code and the next runs recover. Fixes found: DuckDB container ignored SIGTERM (PID 1) so each restart took 30 s - added a handler (now 0.9 s). Observation for later: ClickHouse idle cgroup memory after restart is ~1.2 GB (SF1) vs ~0.09 GB for DuckDB.

## Comments
