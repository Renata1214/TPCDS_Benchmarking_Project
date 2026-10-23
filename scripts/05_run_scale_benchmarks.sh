#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DUCKDB_BIN="${DUCKDB_BIN:-duckdb}"
REFERENCE_SCALE_GB="${REFERENCE_SCALE_GB:-10}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}"
REPEATS="${REPEATS:-1}"
WARMUP_RUNS="${WARMUP_RUNS:-1}"
FACTORS=("$@")

if ((${#FACTORS[@]} == 0)); then
    FACTORS=(0.1 0.2 0.5)
fi

command -v "$DUCKDB_BIN" >/dev/null 2>&1 || {
    printf "ERROR: DuckDB CLI '%s' was not found in PATH.\n" "$DUCKDB_BIN" >&2
    exit 1
}
command -v python3 >/dev/null 2>&1 || {
    printf 'ERROR: Python 3 is required to run the benchmark.\n' >&2
    exit 1
}

exec python3 "$ROOT_DIR/scripts/benchmark_duckdb_session.py" \
    --root "$ROOT_DIR" \
    --duckdb-bin "$DUCKDB_BIN" \
    --reference-scale-gb "$REFERENCE_SCALE_GB" \
    --timeout-seconds "$TIMEOUT_SECONDS" \
    --repeats "$REPEATS" \
    --warmup-runs "$WARMUP_RUNS" \
    "${FACTORS[@]}"
