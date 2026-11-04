# 03 Generate TPC-H Parquet

Type: task
Status: resolved
Blocked by: 02

## Question

Generate SF1 and SF10 with DuckDB tpch dbgen and export each table to Parquet. Gate: row counts match the TPC-H spec formulas for every table and SF.

## Answer

Generated with DuckDB 2.0.0 CALL dbgen in a scratch file DB, exported with COPY ... (FORMAT parquet) (DuckDB defaults: snappy, default row groups). Gate passed: all 16 table x SF row counts equal the TPC-H spec (lineitem 6,001,215 at SF1 and 59,986,052 at SF10). Sizes: SF1 lineitem 205.5 MB, SF10 lineitem 2206.3 MB, SF10 total ~3.4 GB. dbgen time 3.3 s (SF1), 36.6 s (SF10). Schema: keys BIGINT/INTEGER, money DECIMAL(15,2), dates DATE, text VARCHAR. Evidence: results/data_manifest.json.

## Comments
