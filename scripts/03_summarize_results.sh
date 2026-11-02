#!/usr/bin/env bash
# Example: bash scripts/03_summarize_results.sh
# Or specify a report and output: bash scripts/03_summarize_results.sh results/execution_results_<timestamp>.csv results/summary.txt
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$ROOT_DIR" "$@" <<'PY'
import csv
import sys
from pathlib import Path

root = Path(sys.argv[1])
args = sys.argv[2:]
if len(args) > 2:
    raise SystemExit(
        "Usage: bash scripts/03_summarize_results.sh [input.csv] [output.txt]"
    )

if args:
    input_path = Path(args[0]).expanduser().resolve()
else:
    reports = list((root / "results").glob("execution_results_*.csv"))
    if not reports:
        raise SystemExit(
            f"No execution_results_*.csv reports found in {root / 'results'}"
        )
    input_path = max(reports, key=lambda path: path.stat().st_mtime)

if not input_path.is_file():
    raise SystemExit(f"Input report does not exist: {input_path}")

output_path = (
    Path(args[1]).expanduser().resolve()
    if len(args) == 2
    else root / "results" / "query_compatibility_summary.txt"
)

with input_path.open(newline="", encoding="utf-8-sig") as source:
    reader = csv.DictReader(source)
    required = {"query", "status", "elapsed_seconds"}
    missing = required.difference(reader.fieldnames or [])
    if missing:
        raise SystemExit(
            f"Input report is missing required columns: {', '.join(sorted(missing))}"
        )
    rows = list(reader)

status_counts = {}
for row in rows:
    status = row["status"]
    status_counts[status] = status_counts.get(status, 0) + 1

output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", encoding="utf-8", newline="\n") as output:
    output.write("TPC-DS / DuckDB Query Execution Summary\n")
    output.write(f"Input report: {input_path}\n\n")
    output.write("SUMMARY\n")
    output.write(f"Total rows: {len(rows)}\n")
    for status in sorted(status_counts):
        output.write(f"{status}: {status_counts[status]}\n")

    output.write("\nWORKING QUERIES\n")
    for row in rows:
        if row["status"] == "WORKING":
            output.write(
                f"Scale SF{row.get('scale_gb', '')}, query {row['query']}"
                f" -- {row['elapsed_seconds']} seconds\n"
            )

    output.write("\nFAILED / TIMED-OUT / SKIPPED QUERIES\n")
    for row in rows:
        if row["status"] == "WORKING":
            continue
        output.write(
            f"Scale SF{row.get('scale_gb', '')}, query {row['query']}\n"
            f"Status: {row['status']}\n"
            f"Elapsed: {row['elapsed_seconds']} seconds\n"
        )
        if row.get("error_type"):
            output.write(f"Error type: {row['error_type']}\n")
        if row.get("error_summary"):
            output.write(f"Error: {row['error_summary']}\n")
        if row.get("log_file"):
            output.write(f"Full log: {row['log_file']}\n")
        output.write("-" * 60 + "\n")

print(f"Summary written to: {output_path}")
PY
