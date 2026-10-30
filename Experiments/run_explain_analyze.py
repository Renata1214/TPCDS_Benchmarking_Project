#!/usr/bin/env python3
"""Run EXPLAIN ANALYZE for a SQL file against a TPC-DS DuckDB database."""

import argparse
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
EXPLAIN_ANALYZE_PREFIX = re.compile(r"^\s*EXPLAIN\s+ANALYZE\b", re.IGNORECASE)
OPTIMIZER_WRAPPER = re.compile(
    r"\A\s*(?:--[^\r\n]*(?:\r?\n|$)\s*)*"
    r"SET\s+disabled_optimizers\s*=\s*'(?P<setting>[^']*)'\s*;\s*"
    r"(?:EXPLAIN\s+ANALYZE\s+)?(?P<query>.*?)\s*"
    r"SET\s+disabled_optimizers\s*=\s*''\s*;\s*\Z",
    re.IGNORECASE | re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run EXPLAIN ANALYZE for a SQL file and save the text plan."
    )
    parser.add_argument(
        "sql_file",
        type=Path,
        help="SQL file containing one query (may already begin with EXPLAIN ANALYZE).",
    )
    parser.add_argument(
        "--scale-gb",
        type=int,
        default=1,
        help="TPC-DS database scale to use: 1, 2, 4, or 8 (default: 1).",
    )
    parser.add_argument(
        "--runtime",
        choices=("docker", "native"),
        default="docker",
        help="Run the project DuckDB Docker image or a local DuckDB CLI (default: docker).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Optional output text file. By default, create a timestamped "
            "results_explain_analyze_* folder beside the SQL file."
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Maximum time allowed for EXPLAIN ANALYZE (default: 1800).",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=0,
        help="Execute the query this many times before EXPLAIN ANALYZE (default: 0).",
    )
    args = parser.parse_args()
    if args.scale_gb not in (1, 2, 4, 8):
        parser.error("--scale-gb must be one of 1, 2, 4, or 8")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero")
    if args.warmups < 0:
        parser.error("--warmups cannot be negative")
    return args


def build_runtime(runtime: str, scale_gb: int) -> Tuple[List[str], str]:
    database_path = ROOT / "duckdb" / f"tpcds_sf{scale_gb}.duckdb"
    if not database_path.is_file():
        raise SystemExit(f"DuckDB database does not exist: {database_path}")

    if runtime == "docker":
        docker = shutil.which("docker")
        if docker is None:
            raise SystemExit(
                "Docker is not on PATH. Use --runtime native if DuckDB CLI is installed."
            )
        compose_check = subprocess.run(
            [docker, "compose", "version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if compose_check.returncode != 0:
            details = (compose_check.stderr or compose_check.stdout).strip()
            raise SystemExit(f"Docker Compose is not available: {details}")
        return (
            [
                docker,
                "compose",
                "run",
                "--rm",
                "-T",
                "--entrypoint",
                "duckdb",
                "tpcds",
            ],
            f"/workspace/duckdb/tpcds_sf{scale_gb}.duckdb",
        )

    duckdb = shutil.which("duckdb")
    if duckdb is None:
        raise SystemExit("DuckDB CLI is not on PATH.")
    return [duckdb], str(database_path)


def read_sql(sql_file: Path) -> Tuple[str, str]:
    if not sql_file.is_file():
        raise SystemExit(f"SQL file does not exist: {sql_file}")
    try:
        sql = sql_file.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"Could not read SQL file {sql_file}: {error}") from error
    if not sql:
        raise SystemExit(f"SQL file is empty: {sql_file}")
    optimizer_match = OPTIMIZER_WRAPPER.fullmatch(sql)
    if optimizer_match:
        query_sql = optimizer_match.group("query").strip()
        optimizer_setting = optimizer_match.group("setting")
    else:
        query_sql = EXPLAIN_ANALYZE_PREFIX.sub("", sql, count=1).strip()
        optimizer_setting = ""
    if not query_sql:
        raise SystemExit(f"No query SQL found in {sql_file}")
    return query_sql.rstrip().rstrip(";"), optimizer_setting


def output_paths(output: Path, sql_file: Path) -> Tuple[Path, Path]:
    if output.suffix:
        output_file = output.resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = output.resolve()
        output_dir.mkdir(parents=True, exist_ok=False)
        output_file = output_dir / f"{sql_file.stem}_explain_analyze.txt"
    metadata_file = output_file.with_name(
        f"{output_file.stem}_metadata{output_file.suffix or '.txt'}"
    )
    if output_file.exists() or metadata_file.exists():
        raise SystemExit(
            f"Output already exists; choose a new path: {output_file} "
            f"or {metadata_file}"
        )
    return output_file, metadata_file


def main() -> int:
    args = parse_args()
    sql_file = args.sql_file.expanduser().resolve()
    query_sql, optimizer_setting = read_sql(sql_file)
    command, database_argument = build_runtime(args.runtime, args.scale_gb)

    version_process = subprocess.run(
        command + ["--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    if version_process.returncode != 0:
        details = (version_process.stderr or version_process.stdout).strip()
        raise SystemExit(f"Could not get DuckDB version: {details}")
    duckdb_version = version_process.stdout.strip()

    started_at = datetime.now().astimezone()
    started = time.monotonic()
    session_input = (
        f"SET disabled_optimizers = '{optimizer_setting}';\n"
        if optimizer_setting
        else ""
    )
    if args.warmups:
        session_input += ".output /dev/null\n"
        session_input += (query_sql.rstrip().rstrip(";") + ";\n") * args.warmups
        session_input += ".output stdout\n"
    session_input += f"EXPLAIN ANALYZE\n{query_sql};\n"
    if optimizer_setting:
        session_input += (
            "SET disabled_optimizers = '';\n"
            "SELECT current_setting('disabled_optimizers') "
            "AS restored_disabled_optimizers;\n"
        )
    try:
        result = subprocess.run(
            command + ["-batch", "-bail", database_argument],
            input=session_input,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=args.timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise SystemExit(
            f"EXPLAIN ANALYZE exceeded the {args.timeout_seconds}-second timeout."
        ) from error
    elapsed_seconds = time.monotonic() - started
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise SystemExit(
            f"DuckDB EXPLAIN ANALYZE failed with exit code {result.returncode}:\n"
            f"{details}"
        )
    if not result.stdout.strip():
        raise SystemExit("DuckDB completed without returning an EXPLAIN ANALYZE plan.")

    run_id = started_at.strftime("%Y%m%d_%H%M%S_%f")
    if args.output:
        requested_output = args.output.expanduser()
        output_file, metadata_file = output_paths(requested_output, sql_file)
    else:
        output_dir = sql_file.parent / f"results_explain_analyze_{run_id}"
        output_file, metadata_file = output_paths(output_dir, sql_file)

    try:
        with output_file.open("x", encoding="utf-8", newline="") as stream:
            stream.write(result.stdout)
        metadata = [
            f"Run ID: {run_id}",
            f"Started: {started_at.isoformat()}",
            f"SQL file: {sql_file}",
            f"Scale: SF{args.scale_gb}",
            f"Database: {database_argument}",
            f"Runtime: {args.runtime}",
            f"DuckDB: {duckdb_version}",
            "Statement: EXPLAIN ANALYZE",
            f"Warm-up executions before EXPLAIN ANALYZE: {args.warmups}",
            f"Disabled optimizers during execution: {optimizer_setting or '(none)'}",
            (
                "Optimizer setting reset and verified after plan capture."
                if optimizer_setting
                else "Optimizer setting was not changed."
            ),
            f"Timeout seconds: {args.timeout_seconds}",
            f"Elapsed seconds: {elapsed_seconds:.6f}",
            f"Plan output: {output_file}",
        ]
        with metadata_file.open("x", encoding="utf-8", newline="") as stream:
            stream.write("\n".join(metadata) + "\n")
    except OSError as error:
        raise SystemExit(f"Could not save EXPLAIN ANALYZE output: {error}") from error

    print(f"EXPLAIN ANALYZE output: {output_file}")
    print(f"Run metadata: {metadata_file}")
    print(f"DuckDB: {duckdb_version}; elapsed: {elapsed_seconds:.3f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
