#!/usr/bin/env bash
# Example: docker compose run --rm -e REFERENCE_SCALE_GB=10 tpcds bash scripts/run_tpcds.sh --generate-data
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
TOOLS_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/tools"
TEMPLATES_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/query_templates"
QUERY_SCALES=(1 2 4 8)
GENERATE_DATA=0

case "${1:-}" in
    "")
        ;;
    --generate-data)
        GENERATE_DATA=1
        shift
        ;;
    *)
        printf 'Usage: %s [--generate-data]\n' "$0" >&2
        exit 2
        ;;
esac

if (($# > 0)); then
    printf 'Usage: %s [--generate-data]\n' "$0" >&2
    exit 2
fi

FACTORS=(0.1 0.2 0.4 0.8)
BASELINE_ID="20261023_164300_814393"

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

query_dirs=()
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
if ((GENERATE_DATA)); then
    DSDGEN_BIN="$DSDGEN_BIN" bash "$SCRIPTS_DIR/04_generate_scale_data.sh" "${FACTORS[@]}"
else
    for scale in "${QUERY_SCALES[@]}"; do
        database="$ROOT_DIR/duckdb/tpcds_sf${scale}.duckdb"
        [[ -s "$database" ]] ||
            fail "Missing database $database. Run this workflow with --generate-data to create the required data and databases."
    done
    printf 'Skipping data generation; using the existing DuckDB databases.\n'
fi

printf '\n== Running query benchmark: %s ==\n' "${FACTORS[*]}"
BASELINE_RUN="$ROOT_DIR/results/benchmark_runs/$BASELINE_ID"
for scale in "${QUERY_SCALES[@]}"; do
    [[ -s "$BASELINE_RUN/summaries/query_summary_sf${scale}.csv" ]] ||
        fail "Required comparison baseline $BASELINE_ID is missing or incomplete: $BASELINE_RUN/summaries/query_summary_sf${scale}.csv"
done
bash "$SCRIPTS_DIR/05_run_scale_benchmarks.sh" "${FACTORS[@]}"

BENCHMARK_ROOT="$ROOT_DIR/results/benchmark_runs"
mapfile -t RUN_IDS < <(
    find "$BENCHMARK_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' |
        sort
)
((${#RUN_IDS[@]} > 0)) || fail "The benchmark did not create a run directory under $BENCHMARK_ROOT."
RUN_ID="${RUN_IDS[${#RUN_IDS[@]}-1]}"
RUN_DIR="$BENCHMARK_ROOT/$RUN_ID"

printf '\n== Generating benchmark plots ==\n'
python3 "$SCRIPTS_DIR/plot_benchmark_results.py" "$RUN_DIR"

COMPARISON_INDEX=""
printf '\n== Comparing with benchmark %s ==\n' "$BASELINE_ID"
python3 "$SCRIPTS_DIR/compare_benchmark_runs.py" "$BASELINE_RUN" "$RUN_DIR"
COMPARISON_INDEX="$RUN_DIR/plots/comparison_$BASELINE_ID/index.html"

printf '\nTPC-DS workflow completed successfully.\n'
printf 'Benchmark results: %s\n' "$RUN_DIR"
printf 'Benchmark report:  %s/plots/index.html\n' "$RUN_DIR"
if [[ -n "$COMPARISON_INDEX" ]]; then
    printf 'Comparison report: %s\n' "$COMPARISON_INDEX"
    printf 'Comparison table:  %s/query_comparison.csv\n' "$(dirname "$COMPARISON_INDEX")"
fi
