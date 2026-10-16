#!/usr/bin/env bash

RESULTS="/mnt/c/Users/Regina/TPCDS/results"

INPUT="$RESULTS/execution_results.csv"
OUTPUT="$RESULTS/query_compatibility_summary.txt"

working=$(awk -F',' 'NR>1 && $2=="WORKING" {count++} END {print count+0}' "$INPUT")
failed=$(awk -F',' 'NR>1 && $2=="FAILED" {count++} END {print count+0}' "$INPUT")
timeout=$(awk -F',' 'NR>1 && $2=="TIMEOUT" {count++} END {print count+0}' "$INPUT")

total=$((working + failed + timeout))

{
    echo "============================================================"
    echo "TPC-DS / DuckDB Query Compatibility Report"
    echo "============================================================"
    echo
    echo "Database:"
    echo "  tpcds_sf1.duckdb"
    echo
    echo "TPC-DS source:"
    echo "  Official TPC-DS 4.0.0 query templates"
    echo
    echo "Dialect:"
    echo "  Custom duckdb.tpl derived from ansi.tpl"
    echo
    echo "Scale factor:"
    echo "  SF1"
    echo
    echo "------------------------------------------------------------"
    echo "SUMMARY"
    echo "------------------------------------------------------------"
    echo
    echo "Total tested : $total"
    echo "Working      : $working"
    echo "Failed       : $failed"
    echo "Timed out    : $timeout"
    echo
    echo

    echo "============================================================"
    echo "WORKING QUERIES"
    echo "============================================================"
    echo

    awk -F',' '
        NR > 1 && $2 == "WORKING" {
            printf "Query %s -- %s seconds\n", $1, $3
        }
    ' "$INPUT"

    echo
    echo "============================================================"
    echo "FAILED / INCOMPATIBLE QUERIES"
    echo "============================================================"
    echo

} > "$OUTPUT"

# We use Python's CSV parser for the detailed section because
# error descriptions can contain commas.
python3 - "$INPUT" "$OUTPUT" <<'PY'
import csv
import sys

input_file = sys.argv[1]
output_file = sys.argv[2]

with open(input_file, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

with open(output_file, "a", encoding="utf-8") as out:
    for row in rows:
        if row["status"] == "WORKING":
            continue

        out.write(f"Query {row['query']}\n")
        out.write(f"Status: {row['status']}\n")
        out.write(f"Elapsed: {row['elapsed_seconds']} seconds\n")

        if row["error_type"]:
            out.write(f"Error type: {row['error_type']}\n")

        if row["error_summary"]:
            out.write(f"Error: {row['error_summary']}\n")

        out.write(f"Full log: {row['log_file']}\n")
        out.write("-" * 60 + "\n\n")
PY

echo "Summary written to:"
echo "$OUTPUT"
