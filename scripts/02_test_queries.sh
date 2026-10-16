#!/usr/bin/env bash

# ============================================================
# Execute every generated TPC-DS SQL query independently
# against the SF1 DuckDB database.
#
# Each query gets:
#   - its own execution
#   - its own log
#   - execution time
#   - WORKING / FAILED / TIMEOUT classification
# ============================================================

DB="/mnt/c/Users/Regina/TPCDS/duckdb/tpcds_sf1.duckdb"
QUERY_DIR="/mnt/c/Users/Regina/TPCDS/queries/all_templates"
RESULTS="/mnt/c/Users/Regina/TPCDS/results"
LOG_DIR="$RESULTS/logs"

# Prevent one accidental long-running query from blocking the
# complete compatibility test forever.
TIMEOUT_SECONDS=300

mkdir -p "$LOG_DIR"

REPORT="$RESULTS/execution_results.csv"

echo 'query,status,elapsed_seconds,error_type,error_summary,log_file' > "$REPORT"

echo "Testing generated queries against DuckDB..."
echo

for sql_file in $(find "$QUERY_DIR" \
    -maxdepth 1 \
    -type f \
    -name 'query*.sql' |
    sort -V)
do
    filename=$(basename "$sql_file")
    base="${filename%.sql}"
    number="${base#query}"

    log="$LOG_DIR/${base}.log"

    echo "Testing Query $number ..."

    start_ns=$(date +%s%N)

    # Execute this query in an independent DuckDB process.
    #
    # .bail on means DuckDB stops processing this particular
    # file when it encounters an SQL error.
    timeout "$TIMEOUT_SECONDS" \
        duckdb "$DB" \
        -c ".bail on" \
        -c ".read '$sql_file'" \
        > "$log" 2>&1

    rc=$?

    end_ns=$(date +%s%N)

    elapsed=$(awk \
        -v start="$start_ns" \
        -v end="$end_ns" \
        'BEGIN { printf "%.3f", (end-start)/1000000000 }')

    # --------------------------------------------------------
    # TIMEOUT
    # GNU timeout returns 124 if the command exceeded the limit.
    # --------------------------------------------------------
    if [ "$rc" -eq 124 ]; then

        status="TIMEOUT"
        error_type="Timeout"
        summary="Exceeded ${TIMEOUT_SECONDS} seconds"

    # --------------------------------------------------------
    # Detect DuckDB errors from the log.
    # We inspect the log as well as the process return code.
    # --------------------------------------------------------
    elif grep -qiE \
        'Parser Error:|Binder Error:|Catalog Error:|Conversion Error:|Invalid Input Error:|IO Error:|Out of Memory Error:|Internal Error:|Not implemented Error:|TransactionContext Error:|Constraint Error:|HTTP Error:|Error:' \
        "$log"
    then
        status="FAILED"

        error_type=$(grep -im1 -E \
            'Parser Error:|Binder Error:|Catalog Error:|Conversion Error:|Invalid Input Error:|IO Error:|Out of Memory Error:|Internal Error:|Not implemented Error:|TransactionContext Error:|Constraint Error:|HTTP Error:|Error:' \
            "$log" |
            sed 's/^[[:space:]]*//' |
            sed 's/:.*$//' |
            tr ',' ';')

        # Capture the first error and the next few lines.
        summary=$(grep -iA4 -m1 -E \
            'Parser Error:|Binder Error:|Catalog Error:|Conversion Error:|Invalid Input Error:|IO Error:|Out of Memory Error:|Internal Error:|Not implemented Error:|TransactionContext Error:|Constraint Error:|HTTP Error:|Error:' \
            "$log" |
            tr '\n' ' ' |
            sed 's/[[:space:]][[:space:]]*/ /g' |
            sed 's/"/""/g')

    elif [ "$rc" -ne 0 ]; then

        status="FAILED"
        error_type="CLI error"

        summary=$(tail -10 "$log" |
            tr '\n' ' ' |
            sed 's/[[:space:]][[:space:]]*/ /g' |
            sed 's/"/""/g')

    else

        status="WORKING"
        error_type=""
        summary=""

    fi

    echo "$number,$status,$elapsed,\"$error_type\",\"$summary\",\"$log\"" \
        >> "$REPORT"

    printf "  %-8s %s seconds\n" "$status" "$elapsed"
done

echo
echo "Execution test complete."
echo "Results: $REPORT"
echo "Logs:    $LOG_DIR"
