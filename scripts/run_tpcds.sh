#!/usr/bin/env bash
# Example: docker compose run --rm -e REFERENCE_SCALE_GB=10 tpcds bash scripts/run_tpcds.sh 0.1 0.2 0.4 0.8
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
TOOLS_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/tools"
TEMPLATES_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/query_templates"
QUERY_DIR="$ROOT_DIR/queries/all_templates"
QUERY_SCALES=(1 2 4 8)

FACTORS=("$@")
if ((${#FACTORS[@]} == 0)); then
    FACTORS=(0.1 0.2 0.5)
fi

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

DSDGEN_BIN="${DSDGEN_BIN:-$TOOLS_DIR/dsdgen}"
DSQGEN_BIN="${DSQGEN_BIN:-$TOOLS_DIR/dsqgen}"
[[ -x "$DSDGEN_BIN" ]] ||
    fail "Missing Linux dsdgen at $DSDGEN_BIN. Set DSDGEN_BIN to a working executable."
command -v "${DUCKDB_BIN:-duckdb}" >/dev/null 2>&1 ||
    fail "DuckDB CLI was not found. Install it or set DUCKDB_BIN to its executable."
command -v python3 >/dev/null 2>&1 || fail "Python 3 is required."
command -v timeout >/dev/null 2>&1 || fail "GNU timeout is required."
[[ -x /usr/bin/time ]] || fail "GNU time is required at /usr/bin/time."

mapfile -t TEMPLATE_FILES < <(find "$TEMPLATES_DIR" -maxdepth 1 -type f -name 'query*.tpl' -printf '%f\n' | sort -V)
((${#TEMPLATE_FILES[@]} > 0)) || fail "No query templates found under $TEMPLATES_DIR."

query_dirs=("$QUERY_DIR")
for scale in "${QUERY_SCALES[@]}"; do
    query_dirs+=("$ROOT_DIR/queries/sf$scale")
done
queries_ready=1
for query_dir in "${query_dirs[@]}"; do
    for template in "${TEMPLATE_FILES[@]}"; do
        query_file="$query_dir/${template%.tpl}.sql"
        [[ -s "$query_file" ]] || queries_ready=0
    done
done

if [[ "${REGENERATE_QUERIES:-0}" == 1 || "$queries_ready" != 1 ]]; then
    [[ -x "$DSQGEN_BIN" ]] ||
        fail "Query SQL is missing and dsqgen was not found at $DSQGEN_BIN. Set DSQGEN_BIN to a working executable."
    printf '\n== Generating the fixed TPC-DS query workload ==\n'
    DSQGEN_BIN="$DSQGEN_BIN" bash "$SCRIPTS_DIR/01_generate_queries.sh" "${QUERY_SCALES[@]}"
    for query_dir in "${query_dirs[@]}"; do
        for template in "${TEMPLATE_FILES[@]}"; do
            query_file="$query_dir/${template%.tpl}.sql"
            [[ -s "$query_file" ]] || fail "Query generation did not produce $query_file."
        done
    done
else
    printf 'Using existing scale-specific query workloads under %s/queries\n' "$ROOT_DIR"
fi

printf '\n== Generating/loading data factors: %s ==\n' "${FACTORS[*]}"
DSDGEN_BIN="$DSDGEN_BIN" bash "$SCRIPTS_DIR/04_generate_scale_data.sh" "${FACTORS[@]}"

printf '\n== Running query benchmark: %s ==\n' "${FACTORS[*]}"
bash "$SCRIPTS_DIR/05_run_scale_benchmarks.sh" "${FACTORS[@]}"

printf '\nTPC-DS workflow completed successfully.\n'
