#!/usr/bin/env python3
import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


QUERY_FILENAME = re.compile(r"query(\d+)\.sql", re.IGNORECASE)
ERROR_PATTERN = re.compile(
    r"(?:Parser|Binder|Catalog|Conversion|Invalid Input|IO|Out of Memory|"
    r"Internal|Not implemented|TransactionContext|Constraint|HTTP)? Error:",
    re.IGNORECASE,
)
REPORT_FIELDS = [
    "timestamp",
    "factor",
    "scale_gb",
    "query",
    "mode",
    "status",
    "elapsed_seconds",
    "exit_code",
    "error_summary",
    "output_file",
    "query_file",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Save DuckDB EXPLAIN and EXPLAIN ANALYZE output for TPC-DS queries."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the parent of this script directory).",
    )
    parser.add_argument(
        "--duckdb-bin",
        default=os.environ.get("DUCKDB_BIN", "duckdb"),
        help="DuckDB CLI executable (default: DUCKDB_BIN or duckdb).",
    )
    parser.add_argument(
        "--reference-scale-gb",
        type=float,
        default=float(os.environ.get("REFERENCE_SCALE_GB", "10")),
        help="Reference data size used to convert factors to physical scales.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("TIMEOUT_SECONDS", "300")),
        help="Timeout for each EXPLAIN or EXPLAIN ANALYZE (default: 300).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: results/explain_runs/<timestamp>).",
    )
    parser.add_argument(
        "factors",
        nargs="*",
        help="Relative scale factors; defaults to 0.1 0.2 0.5.",
    )
    args = parser.parse_args()
    if args.reference_scale_gb <= 0:
        parser.error("--reference-scale-gb must be greater than zero")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")
    if args.output_dir is None:
        args.output_dir = (
            args.root / "results" / "explain_runs" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        )
    elif not args.output_dir.is_absolute():
        args.output_dir = args.root / args.output_dir
    if not args.factors:
        args.factors = ["0.1", "0.2", "0.5"]
    return args


def factor_scale(factor, reference):
    try:
        numeric_factor = float(factor)
    except ValueError as error:
        raise ValueError(f"invalid factor {factor!r}") from error
    if numeric_factor <= 0:
        raise ValueError(f"factor must be positive: {factor}")
    physical_scale = numeric_factor * reference
    rounded_scale = round(physical_scale)
    if rounded_scale < 1 or abs(physical_scale - rounded_scale) > 1e-7:
        raise ValueError(
            f"factor {factor} produces {physical_scale:g} GB; "
            "the data generator requires whole-number scales of at least 1 GB"
        )
    return numeric_factor, rounded_scale


def query_files_for_scale(query_root, scale_gb):
    query_files = {}
    legacy_dir = query_root / "all_templates"
    scale_dir = query_root / f"sf{scale_gb}"
    for directory in (legacy_dir, scale_dir):
        if not directory.is_dir():
            continue
        for path in directory.glob("query*.sql"):
            match = QUERY_FILENAME.fullmatch(path.name)
            if match and path.is_file():
                query_files[int(match.group(1))] = path
    return query_files


def run_explain(duckdb_bin, database, query_file, mode, timeout_seconds, output_file):
    sql = query_file.read_text(encoding="utf-8-sig").strip()
    if not sql:
        output_file.write_text("ERROR: Query file is empty.\n", encoding="utf-8")
        return "FAILED", "", 1, "Query file is empty."

    statement = f"{mode} {sql}"
    started = time.monotonic()
    try:
        result = subprocess.run(
            [duckdb_bin, str(database), "-c", ".bail on", "-c", statement],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        elapsed = f"{time.monotonic() - started:.3f}"
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output_file.write_text(
            f"{stdout}{stderr}\nERROR: Timed out after {timeout_seconds} seconds.\n",
            encoding="utf-8",
        )
        return "TIMEOUT", elapsed, "", f"Timed out after {timeout_seconds} seconds."

    elapsed = f"{time.monotonic() - started:.3f}"
    combined_output = result.stdout
    if result.stderr:
        combined_output += result.stderr
    output_file.write_text(combined_output, encoding="utf-8")
    error_line = next(
        (line.strip() for line in combined_output.splitlines() if ERROR_PATTERN.search(line)),
        "",
    )
    if result.returncode != 0 or error_line:
        return (
            "FAILED",
            elapsed,
            result.returncode,
            error_line or f"DuckDB exited with status {result.returncode}.",
        )
    return "OK", elapsed, result.returncode, ""


def main():
    args = parse_args()
    root = args.root.resolve()
    duckdb_bin = shutil.which(args.duckdb_bin)
    if duckdb_bin is None:
        raise SystemExit(f"ERROR: DuckDB CLI '{args.duckdb_bin}' was not found in PATH.")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    report_path = args.output_dir / "explain_results.csv"
    failures = 0
    with report_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
        writer.writeheader()

        for factor_input in args.factors:
            try:
                factor_value, scale_gb = factor_scale(
                    factor_input, args.reference_scale_gb
                )
            except ValueError as error:
                raise SystemExit(f"ERROR: {error}") from error
            factor = f"{factor_value:g}"
            tag = f"sf{scale_gb}"
            database = root / "duckdb" / f"tpcds_{tag}.duckdb"
            if not database.is_file():
                raise SystemExit(
                    f"ERROR: Missing database for factor {factor}: {database}. "
                    "Run scripts/04_generate_scale_data.sh first."
                )

            query_files = query_files_for_scale(root / "queries", scale_gb)
            if not query_files:
                raise SystemExit(
                    f"ERROR: No query*.sql files found under "
                    f"{root / 'queries' / tag} or {root / 'queries' / 'all_templates'}. "
                    "Run scripts/01_generate_queries.sh first."
                )

            output_root = args.output_dir / tag
            output_root.mkdir()
            print(f"Factor {factor} ({tag}): {len(query_files)} queries")
            for number, query_file in sorted(query_files.items()):
                for mode, suffix in (
                    ("EXPLAIN", "explain"),
                    ("EXPLAIN ANALYZE", "explain_analyze"),
                ):
                    output_file = output_root / f"query{number}.{suffix}.txt"
                    status, elapsed, exit_code, error_summary = run_explain(
                        duckdb_bin,
                        database,
                        query_file,
                        mode,
                        args.timeout_seconds,
                        output_file,
                    )
                    writer.writerow(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "factor": factor,
                            "scale_gb": scale_gb,
                            "query": f"query{number}",
                            "mode": mode,
                            "status": status,
                            "elapsed_seconds": elapsed,
                            "exit_code": exit_code,
                            "error_summary": error_summary,
                            "output_file": output_file,
                            "query_file": query_file,
                        }
                    )
                    report_file.flush()
                    if status != "OK":
                        failures += 1
                        print(
                            f"  {query_file.name} {mode}: {status}"
                            + (f" ({error_summary})" if error_summary else ""),
                            file=sys.stderr,
                        )

    print(f"Explain outputs: {args.output_dir}")
    print(f"Status report: {report_path}")
    if failures:
        print(f"Completed with {failures} failed or timed-out operation(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
