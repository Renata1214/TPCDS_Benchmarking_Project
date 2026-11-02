#!/usr/bin/env bash
# Example: bash scripts/01_update_experiment_queries.sh 1 2 4 8
set -Eeuo pipefail
export LC_ALL=C

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/tools"
TEMPLATES_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/query_templates"
QUERY_ROOT="$ROOT_DIR/queries"
DSQGEN_BIN="${DSQGEN_BIN:-$TOOLS_DIR/dsqgen}"
QUERIES=(22 47 74)
SCALES=("$@")

if ((${#SCALES[@]} == 0)); then
    SCALES=(1 2 4 8)
fi

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

[[ -x "$DSQGEN_BIN" ]] ||
    fail "Missing executable: $DSQGEN_BIN (set DSQGEN_BIN to a working dsqgen executable)."
[[ -d "$TEMPLATES_DIR" ]] ||
    fail "Missing query templates directory: $TEMPLATES_DIR"

for scale in "${SCALES[@]}"; do
    [[ "$scale" =~ ^[1-9][0-9]*$ ]] ||
        fail "Invalid scale '$scale'; scales must be positive whole-number GB values."
done

mkdir -p "$QUERY_ROOT"
STAGE_DIR="$(mktemp -d "$QUERY_ROOT/.experiment_query_update.XXXXXX")"
cleanup() {
    case "$STAGE_DIR" in
        "$QUERY_ROOT"/.experiment_query_update.*)
            rm -rf -- "$STAGE_DIR"
            ;;
        *)
            printf 'ERROR: Refusing to remove unexpected staging path: %s\n' "$STAGE_DIR" >&2
            ;;
    esac
}
trap cleanup EXIT

cd "$TOOLS_DIR"
for scale in "${SCALES[@]}"; do
    stage_scale="$STAGE_DIR/sf$scale"
    mkdir -p "$stage_scale"
    for query in "${QUERIES[@]}"; do
        template="query${query}.tpl"
        sql_file="$stage_scale/query${query}.sql"
        error_file="$stage_scale/query${query}.stderr"
        if ! "$DSQGEN_BIN" \
            -DIRECTORY "$TEMPLATES_DIR" \
            -TEMPLATE "$template" \
            -DIALECT duckdb \
            -SCALE "$scale" \
            -FILTER Y \
            > "$sql_file" 2> "$error_file"; then
            fail "dsqgen failed for $template at scale $scale GB: $(tr '\n' ' ' < "$error_file")"
        fi
        [[ -s "$sql_file" ]] || fail "dsqgen produced empty SQL for $template at scale $scale GB."
        if grep -q '^ERROR:' "$sql_file"; then
            fail "dsqgen reported a template error for $template at scale $scale GB: $(tr '\n' ' ' < "$sql_file")"
        fi

        if [[ "$query" == 74 ]]; then
            wrapped_file="$stage_scale/query74.wrapped.sql"
            {
                printf "SET disabled_optimizers = 'join_order';\n\n"
                cat "$sql_file"
                printf "\nSET disabled_optimizers = '';\n"
            } > "$wrapped_file"
            mv -- "$wrapped_file" "$sql_file"
        fi
    done
done

for scale in "${SCALES[@]}"; do
    output_dir="$QUERY_ROOT/sf$scale"
    mkdir -p "$output_dir"
    for query in "${QUERIES[@]}"; do
        temporary_file="$(mktemp "$output_dir/.query${query}.sql.XXXXXX")"
        cp -- "$STAGE_DIR/sf$scale/query${query}.sql" "$temporary_file"
        mv -f -- "$temporary_file" "$output_dir/query${query}.sql"
    done
    printf 'Updated Queries 22, 47, and 74 at SF%s.\n' "$scale"
done

if [[ " ${SCALES[*]} " == *" 1 "* ]]; then
    output_dir="$QUERY_ROOT/all_templates"
    mkdir -p "$output_dir"
    for query in "${QUERIES[@]}"; do
        temporary_file="$(mktemp "$output_dir/.query${query}.sql.XXXXXX")"
        cp -- "$QUERY_ROOT/sf1/query${query}.sql" "$temporary_file"
        mv -f -- "$temporary_file" "$output_dir/query${query}.sql"
    done
    printf 'Updated Queries 22, 47, and 74 in all_templates from SF1.\n'
fi
