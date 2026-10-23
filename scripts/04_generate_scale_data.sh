#!/usr/bin/env bash
set -Eeuo pipefail
export LC_ALL=C

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/Kit/DSGen-software-code-4.0.0/tools"
DATA_ROOT="$ROOT_DIR/data"
DB_ROOT="$ROOT_DIR/duckdb"
RESULTS_ROOT="$ROOT_DIR/results"
SCHEMA_FILE="$TOOLS_DIR/tpcds.sql"

REFERENCE_SCALE_GB="${REFERENCE_SCALE_GB:-10}"
FORCE="${FORCE:-0}"
DUCKDB_BIN="${DUCKDB_BIN:-duckdb}"
DSDGEN_BIN="${DSDGEN_BIN:-$TOOLS_DIR/dsdgen}"
DSDGEN_VERBOSE="${DSDGEN_VERBOSE:-Y}"
FACTORS=("$@")
if ((${#FACTORS[@]} == 0)); then
    FACTORS=(0.1 0.2 0.5)
fi

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

scale_in_gb() {
    awk -v reference="$REFERENCE_SCALE_GB" -v factor="$1" \
        'BEGIN { printf "%.8f", reference * factor }'
}

csv_quote() {
    local value="${1//\"/\"\"}"
    printf '"%s"' "$value"
}

[[ -x "$DSDGEN_BIN" ]] || fail "Missing executable: $DSDGEN_BIN (set DSDGEN_BIN to a working dsdgen executable)."
[[ -f "$SCHEMA_FILE" ]] || fail "Missing schema file: $SCHEMA_FILE"
command -v "$DUCKDB_BIN" >/dev/null 2>&1 || fail "DuckDB CLI '$DUCKDB_BIN' was not found in PATH."
[[ "$REFERENCE_SCALE_GB" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "REFERENCE_SCALE_GB must be a positive number."
awk -v value="$REFERENCE_SCALE_GB" 'BEGIN { exit !(value > 0) }' || fail "REFERENCE_SCALE_GB must be greater than zero."
[[ "$FORCE" == 0 || "$FORCE" == 1 ]] || fail "FORCE must be 0 or 1."
[[ "$DSDGEN_VERBOSE" == Y || "$DSDGEN_VERBOSE" == N ]] || fail "DSDGEN_VERBOSE must be Y or N."

TABLES=(
    call_center catalog_page catalog_returns catalog_sales customer
    customer_address customer_demographics date_dim dbgen_version
    household_demographics income_band inventory item promotion reason
    ship_mode store store_returns store_sales time_dim warehouse
    web_page web_returns web_sales web_site
)

mkdir -p "$DATA_ROOT" "$DB_ROOT" "$RESULTS_ROOT"
REPORT="$RESULTS_ROOT/data_generation.csv"
if [[ ! -f "$REPORT" ]]; then
    printf 'started_at,factor,scale_gb,status,elapsed_seconds,data_bytes,database_bytes,database\n' > "$REPORT"
fi

for factor in "${FACTORS[@]}"; do
    [[ "$factor" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "Invalid factor '$factor'; use a positive number such as 0.1."
    awk -v value="$factor" 'BEGIN { exit !(value > 0) }' || fail "Factor '$factor' must be greater than zero."

    calculated_scale_gb="$(scale_in_gb "$factor")"
    awk -v value="$calculated_scale_gb" 'BEGIN { exit !(value >= 1 && value == int(value)) }' ||
        fail "Factor $factor produces ${calculated_scale_gb} GB. dsdgen requires a whole-number scale of at least 1 GB; adjust REFERENCE_SCALE_GB or the factors."
    scale_gb="${calculated_scale_gb%.*}"

    tag="sf${scale_gb}"
    data_dir="$DATA_ROOT/$tag"
    database="$DB_ROOT/tpcds_${tag}.duckdb"

    data_complete=1
    for table in "${TABLES[@]}"; do
        [[ -s "$data_dir/$table.dat" ]] || data_complete=0
    done

    if [[ "$FORCE" != 1 && "$data_complete" == 1 && -f "$database" ]]; then
        data_bytes="$(find "$data_dir" -maxdepth 1 -type f -name '*.dat' -printf '%s\n' | awk '{ total += $1 } END { print total + 0 }')"
        database_bytes="$(stat -c '%s' "$database")"
        printf '%s,%s,%s,EXISTING,0,%s,%s,%s\n' \
            "$(csv_quote "$(date -Is)")" \
            "$(csv_quote "$factor")" \
            "$(csv_quote "$scale_gb")" \
            "$data_bytes" "$database_bytes" \
            "$(csv_quote "$database")" >> "$REPORT"
        printf 'Reusing existing %s data/database for factor %s\n' "$tag" "$factor"
        continue
    fi

    if [[ "$FORCE" != 1 && "$data_complete" != 1 ]]; then
        if [[ -e "$database" || -n "$(find "$data_dir" -maxdepth 1 -type f -name '*.dat' -print -quit 2>/dev/null)" ]]; then
            fail "$tag data is incomplete. Set FORCE=1 to regenerate this scale."
        fi
    fi

    mkdir -p "$data_dir"
    started_at="$(date -Is)"
    started_ns="$(date +%s%N)"
    if [[ "$FORCE" == 1 || "$data_complete" != 1 ]]; then
        printf 'Generating factor %s (%s GB) into %s\n' "$factor" "$scale_gb" "$data_dir"
        (
            cd "$TOOLS_DIR"
            "$DSDGEN_BIN" -SCALE "$scale_gb" -DIR "$data_dir" -FORCE Y -VERBOSE "$DSDGEN_VERBOSE"
        )

        for table in "${TABLES[@]}"; do
            [[ -s "$data_dir/$table.dat" ]] || fail "Generator did not produce $data_dir/$table.dat"
        done
    else
        printf 'Using existing %s data files for factor %s\n' "$data_dir" "$factor"
    fi

    if [[ "$FORCE" == 1 ]]; then
        rm -f -- "$database" "$database.wal"
    fi

    "$DUCKDB_BIN" "$database" < "$SCHEMA_FILE"
    load_sql="$(mktemp)"
    trap 'rm -f -- "$load_sql"' EXIT
    for table in "${TABLES[@]}"; do
        data_file="${data_dir}/${table}.dat"
        escaped_file="${data_file//\'/\'\'}"
        printf "COPY %s FROM '%s' (DELIMITER '|', HEADER false, NULL '');\n" \
            "$table" "$escaped_file" >> "$load_sql"
    done
    "$DUCKDB_BIN" "$database" < "$load_sql"
    rm -f -- "$load_sql"
    trap - EXIT

    data_bytes="$(find "$data_dir" -maxdepth 1 -type f -name '*.dat' -printf '%s\n' | awk '{ total += $1 } END { print total + 0 }')"
    database_bytes="$(stat -c '%s' "$database")"
    ended_ns="$(date +%s%N)"
    elapsed_seconds="$(awk -v start="$started_ns" -v end="$ended_ns" \
        'BEGIN { printf "%.3f", (end - start) / 1000000000 }')"
    printf '%s,%s,%s,GENERATED,%s,%s,%s,%s\n' \
        "$(csv_quote "$started_at")" \
        "$(csv_quote "$factor")" \
        "$(csv_quote "$scale_gb")" \
        "$elapsed_seconds" \
        "$data_bytes" "$database_bytes" \
        "$(csv_quote "$database")" >> "$REPORT"

    printf 'Loaded factor %s: data=%s bytes, database=%s bytes\n' \
        "$factor" "$data_bytes" "$database_bytes"
done

printf 'Generation report: %s\n' "$REPORT"
