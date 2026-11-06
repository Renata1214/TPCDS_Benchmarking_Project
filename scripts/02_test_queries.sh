#!/usr/bin/env bash
# Example: bash scripts/02_test_queries.sh 1 2 4 8
set -Eeuo pipefail
export LC_ALL=C

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DUCKDB_BIN="${DUCKDB_BIN:-duckdb}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
SCALES=("$@")
if ((${#SCALES[@]} == 0)); then
    SCALES=(1 2 4 8)
fi

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

csv_quote() {
    local value="${1//\"/\"\"}"
    printf '"%s"' "$value"
}

command -v "$DUCKDB_BIN" >/dev/null 2>&1 ||
    fail "DuckDB CLI '$DUCKDB_BIN' was not found in PATH."
command -v timeout >/dev/null 2>&1 || fail "GNU timeout is required."
[[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail "TIMEOUT_SECONDS must be a positive integer."

RESULTS="$ROOT_DIR/results"
LOG_ROOT="$RESULTS/logs"
RUN_ID="$(date +%Y%m%d_%H%M%S)"
REPORT="$RESULTS/execution_results_${RUN_ID}.csv"
mkdir -p "$LOG_ROOT"
printf 'scale_gb,query,status,elapsed_seconds,error_type,error_summary,log_file\n' > "$REPORT"

failed=0
skipped=0
tested=0
for scale in "${SCALES[@]}"; do
    [[ "$scale" =~ ^[1-9][0-9]*$ ]] || fail "Invalid scale '$scale'; use positive whole-number GB values."

    tag="sf${scale}"
    query_dir="$ROOT_DIR/queries/$tag"
    database="$ROOT_DIR/duckdb/tpcds_${tag}.duckdb"
    [[ -d "$query_dir" ]] || fail "Missing generated query directory: $query_dir"

    mapfile -t QUERY_FILES < <(
        find "$query_dir" -maxdepth 1 -type f -regextype posix-extended \
            -regex '.*/query[0-9]+\.sql' -printf '%f\n' | sort -V
    )
    ((${#QUERY_FILES[@]} > 0)) || fail "No generated queries found under $query_dir"

    scale_log_dir="$LOG_ROOT/$tag"
    mkdir -p "$scale_log_dir"
    printf '\nTesting %s queries against %s\n' "$tag" "$database"

    for filename in "${QUERY_FILES[@]}"; do
        base="${filename%.sql}"
        number="${base#query}"
        sql_file="$query_dir/$filename"
        log="$scale_log_dir/${base}_${RUN_ID}.log"

        if [[ ! -f "$database" ]]; then
            printf '%s,%s,SKIPPED,0,Missing database,%s,%s\n' \
                "$scale" "$number" \
                "$(csv_quote "No database found at $database")" \
                "$(csv_quote "$log")" >> "$REPORT"
            skipped=$((skipped + 1))
            continue
        fi

        start_ns="$(date +%s%N)"
        if timeout "$TIMEOUT_SECONDS" \
            "$DUCKDB_BIN" "$database" \
            -c ".bail on" \
            -c ".read '$sql_file'" \
            > "$log" 2>&1; then
            rc=0
        else
            rc=$?
        fi
        end_ns="$(date +%s%N)"
        elapsed="$(awk -v start="$start_ns" -v end="$end_ns" \
            'BEGIN { printf "%.3f", (end-start)/1000000000 }')"

        if [[ "$rc" -eq 124 ]]; then
            status="TIMEOUT"
            error_type="Timeout"
            summary="Exceeded ${TIMEOUT_SECONDS} seconds"
        elif grep -qiE \
            'Parser Error:|Binder Error:|Catalog Error:|Conversion Error:|Invalid Input Error:|IO Error:|Out of Memory Error:|Internal Error:|Not implemented Error:|TransactionContext Error:|Constraint Error:|HTTP Error:|Error:' \
            "$log"; then
            status="FAILED"
            error_type="$(grep -im1 -E \
                'Parser Error:|Binder Error:|Catalog Error:|Conversion Error:|Invalid Input Error:|IO Error:|Out of Memory Error:|Internal Error:|Not implemented Error:|TransactionContext Error:|Constraint Error:|HTTP Error:|Error:' \
                "$log" | sed 's/^[[:space:]]*//' | sed 's/:.*$//' | tr ',' ';')"
            summary="$(grep -iA4 -m1 -E \
                'Parser Error:|Binder Error:|Catalog Error:|Conversion Error:|Invalid Input Error:|IO Error:|Out of Memory Error:|Internal Error:|Not implemented Error:|TransactionContext Error:|Constraint Error:|HTTP Error:|Error:' \
                "$log" | tr '\n' ' ' | sed 's/[[:space:]][[:space:]]*/ /g')"
        elif [[ "$rc" -ne 0 ]]; then
            status="FAILED"
            error_type="CLI error"
            summary="$(tail -10 "$log" | tr '\n' ' ' | sed 's/[[:space:]][[:space:]]*/ /g')"
        else
            status="WORKING"
            error_type=""
            summary=""
        fi

        printf '%s,%s,%s,%s,%s,%s,%s\n' \
            "$scale" "$number" "$status" "$elapsed" \
            "$(csv_quote "$error_type")" \
            "$(csv_quote "$summary")" \
            "$(csv_quote "$log")" >> "$REPORT"

        tested=$((tested + 1))
        if [[ "$status" == "WORKING" ]]; then
            printf '  Query %s: %s (%ss)\n' "$number" "$status" "$elapsed"
        else
            failed=$((failed + 1))
            printf '  Query %s: %s (%ss) %s\n' "$number" "$status" "$elapsed" "$error_type" >&2
        fi
    done
done

printf '\nExecution summary: %s tested, %s failed/timeouts, %s skipped (missing database).\n' \
    "$tested" "$failed" "$skipped"
printf 'Report: %s\nLogs: %s\n' "$REPORT" "$LOG_ROOT"

if ((failed > 0)); then
    exit 1
fi
