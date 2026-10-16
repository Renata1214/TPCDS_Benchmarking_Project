#!/usr/bin/env bash

# ============================================================
# Generate one SQL file for every TPC-DS query template
# using the custom DuckDB dialect.
# ============================================================

TOOLS="/mnt/c/Users/Regina/TPCDS/Kit/DSGen-software-code-4.0.0/tools"
TEMPLATES="/mnt/c/Users/Regina/TPCDS/Kit/DSGen-software-code-4.0.0/query_templates"
OUTPUT="/mnt/c/Users/Regina/TPCDS/queries/all_templates"
RESULTS="/mnt/c/Users/Regina/TPCDS/results"

SCALE=1

mkdir -p "$OUTPUT"
mkdir -p "$RESULTS"

# Start with a fresh generation report.
REPORT="$RESULTS/generation_results.csv"

echo 'query,template,generation_status,error' > "$REPORT"

cd "$TOOLS" || exit 1

echo "Generating TPC-DS queries..."

# Find query1.tpl, query2.tpl, ..., and sort them numerically.
find "$TEMPLATES" \
    -maxdepth 1 \
    -type f \
    -name 'query*.tpl' \
    -printf '%f\n' |
sort -V |
while read -r template
do
    # query12.tpl -> query12
    base="${template%.tpl}"

    # query12 -> 12
    number="${base#query}"

    sql_file="$OUTPUT/${base}.sql"
    error_file="$OUTPUT/${base}.generation.err"

    echo "Generating $template ..."

    # Remove output from a previous run.
    rm -f "$sql_file" "$error_file"

    ./dsqgen \
        -DIRECTORY "$TEMPLATES" \
        -TEMPLATE "$template" \
        -DIALECT duckdb \
        -SCALE "$SCALE" \
        -FILTER Y \
        > "$sql_file" \
        2> "$error_file"

    rc=$?

    if [ "$rc" -eq 0 ] && [ -s "$sql_file" ]; then
        echo "$number,$template,OK," >> "$REPORT"
        rm -f "$error_file"
        echo "  OK"
    else
        error=$(tr '\n' ' ' < "$error_file" | sed 's/"/""/g')
        echo "$number,$template,FAILED,\"$error\"" >> "$REPORT"

        # A failed generation should not leave something that looks
        # like a valid SQL query.
        rm -f "$sql_file"

        echo "  FAILED"
    fi
done

echo
echo "Generation finished."
echo "Queries: $OUTPUT"
echo "Report:  $REPORT"
