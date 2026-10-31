#!/usr/bin/env bash

# ============================================================
# Generate one SQL file per TPC-DS query template and scale
# using the custom DuckDB dialect.
# ============================================================

set -Eeuo pipefail
export LC_ALL=C

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/tools"
DSQGEN_BIN="${DSQGEN_BIN:-$TOOLS/dsqgen}"
RNGSEED="${RNGSEED:-}"
TEMPLATES="${TEMPLATE_DIR:-$ROOT_DIR/Kit/DSGen-software-code-4.0.0/query_templates}"
QUERY_ROOT="${QUERY_ROOT:-$ROOT_DIR/queries}"
LEGACY_OUTPUT="$QUERY_ROOT/all_templates"
RESULTS="${RESULTS_DIR:-$ROOT_DIR/results}"

if [[ "$TEMPLATES" != /* ]]; then
    TEMPLATES="$ROOT_DIR/$TEMPLATES"
fi
if [[ "$QUERY_ROOT" != /* ]]; then
    QUERY_ROOT="$ROOT_DIR/$QUERY_ROOT"
    LEGACY_OUTPUT="$QUERY_ROOT/all_templates"
fi
if [[ "$RESULTS" != /* ]]; then
    RESULTS="$ROOT_DIR/$RESULTS"
fi

SCALES=("$@")
if ((${#SCALES[@]} == 0)); then
    if [[ -n "${SCALE:-}" ]]; then
        SCALES=("$SCALE")
    else
        SCALES=(1 2 4 8)
    fi
fi

[[ -x "$DSQGEN_BIN" ]] || {
    printf 'ERROR: Missing executable: %s (set DSQGEN_BIN to a working dsqgen executable)\n' "$DSQGEN_BIN" >&2
    exit 1
}
[[ -d "$TEMPLATES" ]] || {
    printf 'ERROR: Missing query templates directory: %s\n' "$TEMPLATES" >&2
    exit 1
}

if [[ "$DSQGEN_BIN" != /* ]]; then
    DSQGEN_BIN="$PWD/$DSQGEN_BIN"
fi
cd "$TOOLS"

REPORT="$RESULTS/generation_results.csv"
mkdir -p "$QUERY_ROOT" "$RESULTS"
printf 'scale_gb,query,template,generation_status,error\n' > "$REPORT"

mapfile -t TEMPLATES_TO_GENERATE < <(
    find "$TEMPLATES" -maxdepth 1 -type f -name 'query*.tpl' -printf '%f\n' |
        sort -V
)
((${#TEMPLATES_TO_GENERATE[@]} > 0)) || {
    printf 'ERROR: No query templates found in %s\n' "$TEMPLATES" >&2
    exit 1
}

csv_quote() {
    local value="${1//\"/\"\"}"
    printf '"%s"' "$value"
}

failed=0
for scale in "${SCALES[@]}"; do
    [[ "$scale" =~ ^[1-9][0-9]*$ ]] || {
        printf 'ERROR: Invalid scale "%s"; scales must be positive whole-number GB values.\n' "$scale" >&2
        exit 1
    }

    OUTPUT="$QUERY_ROOT/sf$scale"
    mkdir -p "$OUTPUT"
    find "$OUTPUT" -maxdepth 1 -type f -name 'query[0-9]*.sql' -delete
    printf 'Generating TPC-DS queries for scale %s GB...\n' "$scale"

    for template in "${TEMPLATES_TO_GENERATE[@]}"; do
        base="${template%.tpl}"
        number="${base#query}"
        sql_file="$OUTPUT/${base}.sql"
        error_file="$OUTPUT/${base}.generation.err"

        rm -f -- "$sql_file" "$error_file"
        dsqgen_args=(
            -DIRECTORY "$TEMPLATES"
            -TEMPLATE "$template"
            -DIALECT duckdb
            -SCALE "$scale"
            -FILTER Y
        )
        if [[ -n "$RNGSEED" ]]; then
            dsqgen_args+=(-RNGSEED "$RNGSEED")
        fi
        if (
            "$DSQGEN_BIN" "${dsqgen_args[@]}"
        ) > "$sql_file" 2> "$error_file" && [[ -s "$sql_file" ]]; then
            if [[ "$base" == "query74" ]]; then
                wrapped_file="$(mktemp "$OUTPUT/.query74.sql.XXXXXX")"
                if {
                    printf "SET disabled_optimizers = 'join_order';\n\n"
                    cat "$sql_file"
                    printf "\nSET disabled_optimizers = '';\n"
                } > "$wrapped_file"; then
                    mv -f -- "$wrapped_file" "$sql_file"
                else
                    rm -f -- "$wrapped_file"
                    printf 'ERROR: Could not add Query 74 optimizer settings for scale %s GB.\n' "$scale" >&2
                    exit 1
                fi
            fi
            printf '%s,%s,%s,OK,\n' "$scale" "$number" "$template" >> "$REPORT"
            rm -f -- "$error_file"
        else
            error="$(tr '\n' ' ' < "$error_file" | sed 's/"/""/g')"
            printf '%s,%s,%s,FAILED,%s\n' \
                "$scale" "$number" "$template" "$(csv_quote "$error")" >> "$REPORT"
            rm -f -- "$sql_file"
            failed=$((failed + 1))
            printf '  FAILED: %s at scale %s GB\n' "$template" "$scale" >&2
        fi
    done

    generated_count="$(find "$OUTPUT" -maxdepth 1 -type f -name 'query[0-9]*.sql' | wc -l)"
    if ((generated_count != ${#TEMPLATES_TO_GENERATE[@]})); then
        printf 'ERROR: Generated %s of %s queries for scale %s GB.\n' \
            "$generated_count" "${#TEMPLATES_TO_GENERATE[@]}" "$scale" >&2
        failed=$((failed + 1))
    fi
done

if [[ -d "$QUERY_ROOT/sf1" ]]; then
    mkdir -p "$LEGACY_OUTPUT"
    find "$LEGACY_OUTPUT" -maxdepth 1 -type f -name 'query[0-9]*.sql' -delete
    cp "$QUERY_ROOT/sf1"/query[0-9]*.sql "$LEGACY_OUTPUT"/
fi

echo
if ((failed > 0)); then
    printf 'Generation finished with %s failure(s).\n' "$failed" >&2
    printf 'Report: %s\n' "$REPORT" >&2
    exit 1
fi

echo "Generation finished."
printf 'Scale-specific queries:'
for scale in "${SCALES[@]}"; do
    printf ' %s/sf%s' "$QUERY_ROOT" "$scale"
done
printf '\n'
echo "Legacy SF1 queries:    $LEGACY_OUTPUT"
echo "Report:                $REPORT"
