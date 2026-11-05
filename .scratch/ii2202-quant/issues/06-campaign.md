# 06 Full pilot campaign

Type: task
Status: resolved
Blocked by: 05

## Question

Run 3 loads x 2 engines x 2 SF and 2 x 2 x 8 x 21 query runs. Gate: 12 load rows and 672 run rows; latencies > 0; peak <= 8 GiB; SF10 median >= SF1 median, or a documented explanation.

## Answer

Campaign completed 2026-11-05 (log in results/tmp, not committed). Gate passed (scripts/check_runs.py, results/stats/gate2.json): 672 query rows (32 blocks x 21, run_idx 0 = cold), 12 load rows, 0 errors, all 672 results equal the verified checksum, all latencies > 0, max query peak 4.89 GiB <= 8 GiB, SF10 warm median >= SF1 for all 16 engine x query pairs. Independent pandas cross-check agrees. Sampling interval median 3.49 ms, max 4.76 ms; sampled peak vs kernel memory.peak gap median 0, max 2.0%. Notes for the report: (1) load peaks at SF10 reach the 8 GiB cgroup limit for both engines because written/read file pages are charged to the container; anon peaks are 2.7-3.3 GiB; ClickHouse SF10 rep3 shows memory.current 225 KB above memory.max, a transient cgroup charge overshoot, not a failure. (2) A first campaign was aborted during the SF10 loads to add anon memory to load rows; its 9 load rows are kept in results/aborted/load_runs_v1_no_anon.csv and are not used. (3) DuckDB CHECKPOINT at SF10 takes ~3 ms because DuckDB already checkpointed automatically during the load.

## Comments
