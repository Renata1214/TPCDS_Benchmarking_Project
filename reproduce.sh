#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-}" in
    "")
        ;;
    --generate-data)
        ;;
    *)
        printf 'Usage: %s [--generate-data]\n' "$0" >&2
        exit 2
        ;;
esac

if (($# > 1)); then
    printf 'Usage: %s [--generate-data]\n' "$0" >&2
    exit 2
fi

cd "$ROOT_DIR"
docker compose build tpcds
docker compose run --rm \
    -e REFERENCE_SCALE_GB="${REFERENCE_SCALE_GB:-10}" \
    -e WARMUP_RUNS="${WARMUP_RUNS:-1}" \
    -e REPEATS="${REPEATS:-5}" \
    -e TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}" \
    -e REGENERATE_QUERIES=1 \
    tpcds bash scripts/run_tpcds.sh "$@"
