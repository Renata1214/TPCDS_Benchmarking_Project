#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGINAL_TEMPLATES="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/query_templates"
OPTIMIZED_TEMPLATES="${OPTIMIZED_TEMPLATE_DIR:-$ROOT_DIR/query_templates_optimized}"
CHECK_ONLY=0

if [[ "${1:-}" == "--check-only" ]]; then
    CHECK_ONLY=1
    shift
fi

[[ -d "$ORIGINAL_TEMPLATES" ]] || {
    printf 'ERROR: Missing original template directory: %s\n' "$ORIGINAL_TEMPLATES" >&2
    exit 1
}
[[ -d "$OPTIMIZED_TEMPLATES" ]] || {
    printf 'ERROR: Missing optimized template directory: %s\n' "$OPTIMIZED_TEMPLATES" >&2
    exit 1
}

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf -- "$BUILD_DIR"' EXIT
cp -a "$ORIGINAL_TEMPLATES/." "$BUILD_DIR/"

shopt -s nullglob
OPTIMIZED_FILES=("$OPTIMIZED_TEMPLATES"/query*.tpl)
((${#OPTIMIZED_FILES[@]} > 0)) || {
    printf 'ERROR: No optimized query templates found in %s\n' "$OPTIMIZED_TEMPLATES" >&2
    exit 1
}

for optimized_file in "${OPTIMIZED_FILES[@]}"; do
    template_name="${optimized_file##*/}"
    [[ -f "$ORIGINAL_TEMPLATES/$template_name" ]] || {
        printf 'ERROR: No original template exists for %s\n' "$template_name" >&2
        exit 1
    }
    cp -- "$optimized_file" "$BUILD_DIR/$template_name"
done

QUERY_TEMPLATES=("$BUILD_DIR"/query*.tpl)
((${#QUERY_TEMPLATES[@]} == 99)) || {
    printf 'ERROR: Combined workload has %s query templates; expected 99.\n' \
        "${#QUERY_TEMPLATES[@]}" >&2
    exit 1
}

for query_number in {1..99}; do
    [[ -f "$BUILD_DIR/query${query_number}.tpl" ]] || {
        printf 'ERROR: Combined workload is missing query%s.tpl\n' "$query_number" >&2
        exit 1
    }
done

if grep -Eiq '(^|[^[:alnum:]_])materialized([^[:alnum:]_]|$)' "${QUERY_TEMPLATES[@]}"; then
    printf 'ERROR: Combined templates contain a MATERIALIZED hint.\n' >&2
    exit 1
fi

if ((CHECK_ONLY)); then
    printf 'Validated complete combined workload: 99 query templates; no MATERIALIZED hints.\n'
    exit 0
fi

TEMPLATE_DIR="$BUILD_DIR" bash "$ROOT_DIR/scripts/01_generate_queries.sh" "$@"