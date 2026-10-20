#!/usr/bin/env bash

set -uo pipefail

# Override any of these settings through environment variables.
BASE="${BASE:-/work/TPC-DS}"
GENERATED="${GENERATED:-$BASE/sql/generated}"
TIMINGS="${TIMINGS:-$BASE/results/sf1/timings}"
DB="${DB:-$BASE/tpcds_sf1.duckdb}"
DUCKDB="${DUCKDB:-/opt/duckdb/duckdb}"

has_sql_error() {
    grep -Eiq \
      '(Parser Error|Binder Error|Catalog Error|Conversion Error|Constraint Error|Invalid Input Error|Not implemented Error|IOException|Fatal Error|Internal Error)' \
      "$1"
}

if [[ ! -x "$DUCKDB" ]]; then
    echo "ERROR: DuckDB executable not found or not executable: $DUCKDB"
    exit 1
fi

if [[ ! -f "$DB" ]]; then
    echo "ERROR: SF1 database not found: $DB"
    exit 1
fi

if [[ "$#" -eq 0 ]]; then
    echo "Usage: $0 QUERY_NUMBER [QUERY_NUMBER ...]"
    echo "Example: $0 26 27 28"
    exit 1
fi

mkdir -p "$TIMINGS"

for N in "$@"; do
    if [[ ! "$N" =~ ^[0-9]+$ ]]; then
        echo "SKIP: Invalid query number: $N"
        continue
    fi

    printf '\n========== SF1 QUERY %s ==========\n' "$N"

    SQL="$GENERATED/query${N}.sql"
    TEST="$TIMINGS/query${N}_test.txt"
    LOG="$TIMINGS/query${N}_same_process.txt"
    BENCH="$TIMINGS/query${N}_benchmark.sql"

    if [[ ! -s "$SQL" ]]; then
        echo "SKIP: SQL file missing or empty: $SQL"
        continue
    fi

    echo "Database: $DB"
    echo "SQL: $SQL"
    echo "Testing query..."

    if ! "$DUCKDB" "$DB" < "$SQL" > "$TEST" 2>&1; then
        echo "TEST FAILED: DuckDB returned a non-zero exit code; see $TEST"
        continue
    fi

    if has_sql_error "$TEST"; then
        echo "TEST FAILED: SQL error detected; see $TEST"
        grep -Ein \
          '(Parser Error|Binder Error|Catalog Error|Conversion Error|Constraint Error|Invalid Input Error|Not implemented Error|IOException|Fatal Error|Internal Error)' \
          "$TEST" || true
        continue
    fi

    # Run the same SQL five times in one DuckDB process.
    for i in 1 2 3 4 5; do
        cat "$SQL"
        echo
    done > "$BENCH"

    if ! "$DUCKDB" "$DB" -cmd ".timer on" < "$BENCH" > "$LOG" 2>&1; then
        echo "BENCHMARK FAILED: see $LOG"
        continue
    fi

    if has_sql_error "$LOG"; then
        echo "BENCHMARK FAILED: SQL error detected; see $LOG"
        grep -Ein \
          '(Parser Error|Binder Error|Catalog Error|Conversion Error|Constraint Error|Invalid Input Error|Not implemented Error|IOException|Fatal Error|Internal Error)' \
          "$LOG" || true
        continue
    fi

    COUNT=$(grep -c 'Run Time (s)' "$LOG" || true)

    if [[ "$COUNT" -lt 5 ]]; then
        echo "BENCHMARK INCOMPLETE: found $COUNT timing entries; see $LOG"
        continue
    fi

    echo "BENCHMARK FINISHED: $COUNT timing entries"
    grep 'Run Time (s)' "$LOG"
    echo "Test output: $TEST"
    echo "Timing log: $LOG"
done
