#!/usr/bin/env python3
# Example: REFERENCE_SCALE_GB=10 python3 scripts/explain_duckdb_queries.py --warmup-rounds 1 0.1 0.2 0.4 0.8

import argparse
import csv
import os
import re
import selectors
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
    "warmup_rounds",
    "warmup_status",
    "session_id",
    "duckdb_version",
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
        "--warmup-rounds",
        type=int,
        default=1,
        help="Complete workload rounds to execute before collecting plans (default: 1).",
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
    if args.timeout_seconds <= 0 or args.warmup_rounds < 0:
        parser.error("timeout must be positive and warmup rounds cannot be negative")
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


class QueryTimeout(Exception):
    pass


class DuckDBSessionError(Exception):
    pass


class DuckDBSession:
    def __init__(self, executable, database):
        self.process = subprocess.Popen(
            [executable, str(database)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = bytearray()
        self.marker_counter = 0
        self._send_marker("__TPCDS_SESSION_READY__")
        self._wait_for_marker("__TPCDS_SESSION_READY__", time.monotonic() + 30)

    def _send(self, data):
        if self.process.poll() is not None:
            raise DuckDBSessionError(
                f"DuckDB exited with code {self.process.returncode}"
            )
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise DuckDBSessionError("Could not send input to DuckDB") from error

    def _send_marker(self, marker):
        self._send(f".print {marker}\n".encode("ascii"))

    def _next_line(self, deadline):
        while True:
            newline = self.pending.find(b"\n")
            if newline >= 0:
                line = bytes(self.pending[:newline])
                del self.pending[: newline + 1]
                return line.decode("utf-8", errors="replace").rstrip("\r")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QueryTimeout()
            events = self.selector.select(min(remaining, 0.1))
            if not events:
                if self.process.poll() is not None:
                    raise DuckDBSessionError(
                        f"DuckDB exited with code {self.process.returncode}"
                    )
                continue
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except OSError as error:
                raise DuckDBSessionError("Could not read DuckDB output") from error
            if not chunk:
                raise DuckDBSessionError(
                    f"DuckDB exited with code {self.process.poll()}"
                )
            self.pending.extend(chunk)

    def _wait_for_marker(self, marker, deadline):
        while True:
            if self._next_line(deadline).strip() == marker:
                return

    def execute(self, sql, timeout_seconds, capture_output=True):
        if not sql.strip():
            return "", "Query file is empty.", 0.0
        self.marker_counter += 1
        start_marker = f"__TPCDS_BEGIN_{self.marker_counter}__"
        end_marker = f"__TPCDS_END_{self.marker_counter}__"
        self._send_marker(start_marker)
        self._wait_for_marker(start_marker, time.monotonic() + 30)

        statement = sql.strip()
        if not statement.endswith(";"):
            statement += ";"
        started = time.monotonic()
        self._send(statement.encode("utf-8") + b"\n")
        self._send_marker(end_marker)
        deadline = started + timeout_seconds
        output_lines = []
        while True:
            line = self._next_line(deadline)
            if line.strip() == end_marker:
                break
            if capture_output or ERROR_PATTERN.search(line):
                output_lines.append(line)
        output = "\n".join(output_lines)
        error_line = next(
            (line.strip() for line in output_lines if ERROR_PATTERN.search(line)),
            "",
        )
        return output, error_line, time.monotonic() - started

    def close(self):
        if self.process.poll() is None:
            try:
                self._send(b".quit\n")
                self.process.wait(timeout=5)
            except (DuckDBSessionError, subprocess.TimeoutExpired):
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
        self.selector.close()
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stdin:
            self.process.stdin.close()

    def terminate(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.selector.close()
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stdin:
            self.process.stdin.close()


def main():
    args = parse_args()
    root = args.root.resolve()
    duckdb_bin = shutil.which(args.duckdb_bin)
    if duckdb_bin is None:
        raise SystemExit(f"ERROR: DuckDB CLI '{args.duckdb_bin}' was not found in PATH.")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    report_path = args.output_dir / "explain_results.csv"
    warmup_report_path = args.output_dir / "warmup_results.csv"
    duckdb_version = subprocess.run(
        [duckdb_bin, "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    metadata_path = args.output_dir / "metadata.txt"
    metadata_path.write_text(
        "\n".join(
            [
                f"Run started: {datetime.now(timezone.utc).isoformat()}",
                f"Reference scale: {args.reference_scale_gb:g} GB",
                f"Factors: {' '.join(args.factors)}",
                f"Warm-up rounds per scale: {args.warmup_rounds}",
                "Warm-up protocol: complete query passes in ascending query order, using the same persistent DuckDB session as plan capture.",
                "Plan capture order: EXPLAIN then EXPLAIN ANALYZE for each query after all warm-up rounds complete.",
                f"Timeout per statement: {args.timeout_seconds} seconds",
                f"DuckDB: {duckdb_version}",
                f"Platform: {sys.platform}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    failures = 0
    with (
        report_path.open("w", newline="", encoding="utf-8") as report_file,
        warmup_report_path.open("w", newline="", encoding="utf-8") as warmup_report_file,
    ):
        writer = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        warmup_writer = csv.DictWriter(
            warmup_report_file,
            fieldnames=[
                "timestamp",
                "factor",
                "scale_gb",
                "warmup_round",
                "execution_position",
                "query",
                "status",
                "elapsed_seconds",
                "error_summary",
                "query_file",
            ],
        )
        warmup_writer.writeheader()

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
            ordered_queries = sorted(query_files.items())
            session_id = f"{args.output_dir.name}_{tag}"
            print(
                f"Factor {factor} ({tag}): {len(ordered_queries)} queries; "
                f"{args.warmup_rounds} warm-up round(s)"
            )
            warmup_statuses = {number: [] for number, _ in ordered_queries}
            session = None
            try:
                session = DuckDBSession(duckdb_bin, database)
                for warmup_round in range(1, args.warmup_rounds + 1):
                    for position, (number, query_file) in enumerate(
                        ordered_queries, start=1
                    ):
                        query_sql = query_file.read_text(
                            encoding="utf-8-sig"
                        ).strip()
                        status = "OK"
                        error_summary = ""
                        started = time.monotonic()
                        try:
                            _, error_summary, elapsed = session.execute(
                                query_sql,
                                args.timeout_seconds,
                                capture_output=False,
                            )
                            if error_summary:
                                status = "FAILED"
                        except QueryTimeout:
                            elapsed = time.monotonic() - started
                            status = "TIMEOUT"
                            error_summary = (
                                f"Timed out after {args.timeout_seconds} seconds."
                            )
                        except DuckDBSessionError as error:
                            elapsed = time.monotonic() - started
                            status = "FAILED"
                            error_summary = str(error)
                        warmup_statuses[number].append(status)
                        warmup_writer.writerow(
                            {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "factor": factor,
                                "scale_gb": scale_gb,
                                "warmup_round": warmup_round,
                                "execution_position": position,
                                "query": f"query{number}",
                                "status": status,
                                "elapsed_seconds": f"{elapsed:.3f}",
                                "error_summary": error_summary,
                                "query_file": query_file,
                            }
                        )
                        warmup_report_file.flush()
                        if status != "OK":
                            failures += 1
                            print(
                                f"  warm-up {warmup_round} {query_file.name}: {status}"
                                + (f" ({error_summary})" if error_summary else ""),
                                file=sys.stderr,
                            )
                        if status == "TIMEOUT" or session.process.poll() is not None:
                            raise DuckDBSessionError(
                                f"DuckDB session stopped during warm-up of {query_file.name}; "
                                "plan capture for this scale was not completed."
                            )

                for number, query_file in ordered_queries:
                    query_sql = query_file.read_text(
                        encoding="utf-8-sig"
                    ).strip()
                    warmup_status = (
                        ",".join(warmup_statuses[number]) or "NOT_RUN"
                    )
                    for mode, suffix in (
                        ("EXPLAIN", "explain"),
                        ("EXPLAIN ANALYZE", "explain_analyze"),
                    ):
                        output_file = output_root / f"query{number}.{suffix}.txt"
                        started = time.monotonic()
                        try:
                            output, error_summary, elapsed = session.execute(
                                f"{mode} {query_sql}",
                                args.timeout_seconds,
                            )
                            status = "FAILED" if error_summary else "OK"
                            exit_code = 1 if error_summary else 0
                        except QueryTimeout:
                            elapsed = time.monotonic() - started
                            output = ""
                            status = "TIMEOUT"
                            exit_code = 124
                            error_summary = (
                                f"Timed out after {args.timeout_seconds} seconds."
                            )
                        except DuckDBSessionError as error:
                            elapsed = time.monotonic() - started
                            output = ""
                            status = "FAILED"
                            exit_code = 1
                            error_summary = str(error)
                        output_file.write_text(
                            output.rstrip() + ("\n" if output else ""),
                            encoding="utf-8",
                        )
                        writer.writerow(
                            {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "factor": factor,
                                "scale_gb": scale_gb,
                                "query": f"query{number}",
                                "warmup_rounds": args.warmup_rounds,
                                "warmup_status": warmup_status,
                                "session_id": session_id,
                                "duckdb_version": duckdb_version,
                                "mode": mode,
                                "status": status,
                                "elapsed_seconds": f"{elapsed:.3f}",
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
                        if status == "TIMEOUT" or session.process.poll() is not None:
                            raise DuckDBSessionError(
                                f"DuckDB session stopped while capturing {mode} for "
                                f"{query_file.name}; plan capture for this scale "
                                "was not completed."
                            )
            except DuckDBSessionError as error:
                failures += 1
                print(f"  {tag}: {error}", file=sys.stderr)
                if session is not None:
                    session.terminate()
                return 1
            finally:
                if session is not None:
                    session.close()

    print(f"Explain outputs: {args.output_dir}")
    print(f"Status report: {report_path}")
    print(f"Warm-up report: {warmup_report_path}")
    print(f"Run metadata: {metadata_path}")
    if failures:
        print(f"Completed with {failures} failed or timed-out operation(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
