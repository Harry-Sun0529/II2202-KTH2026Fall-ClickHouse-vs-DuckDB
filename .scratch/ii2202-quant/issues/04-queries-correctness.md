# 04 Queries and correctness gate

Type: task
Status: resolved
Blocked by: 03

## Question

Write the 8 queries in both dialects with only necessary edits. Gate: DuckDB SF1 results equal tpch_answers(); both engines return identical rows_returned and checksum (floats rounded to 2 dp) at SF1 and SF10. Does Q21 run on ClickHouse?

## Answer

Query texts: DuckDB tpch extension tpch_queries() (qgen default substitution parameters, the ones the reference answers use), stored verbatim in queries/duckdb/. ClickHouse 26.8 runs all 8 texts unchanged, including Q21's correlated EXISTS/NOT EXISTS and Q13's derived-column alias list, so Q21 needs no rewrite or replacement. One dialect edit: Q13 on ClickHouse adds SETTINGS join_use_nulls = 1. Without it ClickHouse fills unmatched LEFT JOIN rows with 0 instead of NULL, count(o_orderkey) counts them, and c_count=0 (50,005 customers) is merged into c_count=1 (41 rows instead of 42) - caught by the gate. Gate passed: SF1 both engines equal tpch_answers() for all 8 queries (row order, numbers within 0.01, text exact); SF1 and SF10 both engines have identical rows_returned and checksum (2-dp, order-insensitive). Negative tests confirmed the checker rejects: unpatched Q13, +0.02 on Q6, swapped rows, a wrong date, a wrong name. Evidence: results/verification.csv. ClickHouse entrypoint needed CLICKHOUSE_DO_NOT_CHOWN=1 because the Parquet volume is mounted read-only.

## Comments
