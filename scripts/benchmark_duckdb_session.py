#!/usr/bin/env python3
import argparse
import csv
import os
import re
import selectors
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ERROR_PATTERN = re.compile(
    r"(?:Parser|Binder|Catalog|Conversion|Invalid Input|IO|Out of Memory|"
    r"Internal|Not implemented|TransactionContext|Constraint|HTTP)? Error:",
    re.IGNORECASE,
)
METRIC_FIELDS = [
    "timestamp",
    "run_id",
    "factor",
    "scale_gb",
    "query",
    "iteration",
    "status",
    "elapsed_seconds",
    "user_cpu_seconds",
    "system_cpu_seconds",
    "max_rss_kb",
    "exit_code",
    "error_summary",
    "database_bytes",
    "query_file",
    "log_file",
]
SUMMARY_FIELDS = [
    "factor",
    "scale_gb",
    "query",
    "warmup_runs",
    "warmup_failures",
    "runs",
    "working",
    "failed",
    "timeouts",
    "median_elapsed_seconds",
    "mean_elapsed_seconds",
    "mean_user_cpu_seconds",
    "mean_system_cpu_seconds",
    "max_rss_kb",
]


class QueryTimeout(Exception):
    pass


class SessionEnded(Exception):
    pass


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--duckdb-bin", required=True)
    parser.add_argument("--reference-scale-gb", type=float, required=True)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--repeats", type=int, required=True)
    parser.add_argument("--warmup-runs", type=int, required=True)
    parser.add_argument("factors", nargs="+")
    args = parser.parse_args()
    if args.reference_scale_gb <= 0:
        parser.error("--reference-scale-gb must be greater than zero")
    if args.timeout_seconds <= 0 or args.repeats <= 0 or args.warmup_runs < 0:
        parser.error("timeout and repeats must be positive; warmup-runs cannot be negative")
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


def process_cpu_ticks(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields = stat[stat.rfind(")") + 2 :].split()
        return int(fields[11]), int(fields[12])
    except (OSError, IndexError, ValueError):
        return None


def process_rss_kb(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text(encoding="ascii").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return None


class DuckDBSession:
    def __init__(self, executable, database, timeout_seconds):
        self.timeout_seconds = timeout_seconds
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
        self.pid = self.process.pid
        self.cpu_ticks_per_second = os.sysconf("SC_CLK_TCK")
        self.marker_counter = 0
        self.send(b".timer on\n")
        self.marker_counter += 1
        self.send(f".print __TPCDS_READY_{self.marker_counter}__\n".encode("ascii"))
        self.wait_for_marker(f"__TPCDS_READY_{self.marker_counter}__", time.monotonic() + 30, None)

    def send(self, data):
        if self.process.poll() is not None:
            raise SessionEnded(f"DuckDB exited with code {self.process.returncode}")
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise SessionEnded("Could not send input to DuckDB") from error

    def next_line(self, deadline, log_file):
        while True:
            newline = self.pending.find(b"\n")
            if newline >= 0:
                line = bytes(self.pending[:newline])
                del self.pending[: newline + 1]
                if log_file is not None:
                    log_file.write(line.decode("utf-8", errors="replace") + "\n")
                return line.decode("utf-8", errors="replace").rstrip("\r")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QueryTimeout()
            events = self.selector.select(min(remaining, 0.1))
            if not events:
                if self.process.poll() is not None:
                    raise SessionEnded(f"DuckDB exited with code {self.process.returncode}")
                continue
            try:
                chunk = os.read(self.process.stdout.fileno(), 65536)
            except OSError as error:
                raise SessionEnded("Could not read DuckDB output") from error
            if not chunk:
                raise SessionEnded(f"DuckDB exited with code {self.process.poll()}")
            self.pending.extend(chunk)

    def wait_for_marker(self, marker, deadline, log_file):
        while True:
            line = self.next_line(deadline, log_file)
            if line.strip() == marker:
                return

    def execute(self, query_sql, log_file=None):
        self.marker_counter += 1
        start_marker = f"__TPCDS_BEGIN_{self.marker_counter}__"
        end_marker = f"__TPCDS_END_{self.marker_counter}__"
        self.send(f".print {start_marker}\n".encode("ascii"))
        self.wait_for_marker(start_marker, time.monotonic() + 30, log_file)

        start_time = time.monotonic()
        start_cpu = process_cpu_ticks(self.pid)
        peak_rss = process_rss_kb(self.pid)
        self.send(query_sql.encode("utf-8") + b"\n")
        self.send(f".print {end_marker}\n".encode("ascii"))
        deadline = start_time + self.timeout_seconds
        output_lines = []
        while True:
            current_rss = process_rss_kb(self.pid)
            if current_rss is not None:
                peak_rss = max(peak_rss or current_rss, current_rss)
            try:
                line = self.next_line(min(deadline, time.monotonic() + 0.1), log_file)
            except QueryTimeout:
                if time.monotonic() >= deadline:
                    raise
                continue
            if line.strip() == end_marker:
                break
            output_lines.append(line)

        elapsed = time.monotonic() - start_time
        end_cpu = process_cpu_ticks(self.pid)
        user_cpu = None
        system_cpu = None
        if start_cpu is not None and end_cpu is not None:
            user_cpu = max(0, end_cpu[0] - start_cpu[0]) / self.cpu_ticks_per_second
            system_cpu = max(0, end_cpu[1] - start_cpu[1]) / self.cpu_ticks_per_second

        output = "\n".join(output_lines)
        error_line = next(
            (line.strip() for line in output_lines if ERROR_PATTERN.search(line)),
            "",
        )
        return {
            "elapsed_seconds": f"{elapsed:.3f}",
            "user_cpu_seconds": f"{user_cpu:.3f}" if user_cpu is not None else "",
            "system_cpu_seconds": f"{system_cpu:.3f}" if system_cpu is not None else "",
            "max_rss_kb": peak_rss if peak_rss is not None else "",
            "status": "FAILED" if error_line else "WORKING",
            "error_summary": error_line,
            "exit_code": 1 if error_line else 0,
        }

    def close(self):
        if self.process.poll() is None:
            try:
                self.send(b".quit\n")
                self.process.wait(timeout=5)
            except (SessionEnded, subprocess.TimeoutExpired):
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


def write_metric(writer, run_id, factor, scale_gb, query, iteration, result, database_bytes, query_file, log_file):
    writer.writerow(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "factor": factor,
            "scale_gb": scale_gb,
            "query": query,
            "iteration": iteration,
            "status": result["status"],
            "elapsed_seconds": result.get("elapsed_seconds", ""),
            "user_cpu_seconds": result.get("user_cpu_seconds", ""),
            "system_cpu_seconds": result.get("system_cpu_seconds", ""),
            "max_rss_kb": result.get("max_rss_kb", ""),
            "exit_code": result.get("exit_code", ""),
            "error_summary": result.get("error_summary", ""),
            "database_bytes": database_bytes,
            "query_file": str(query_file),
            "log_file": str(log_file) if log_file else "",
        }
    )


def summarize(metrics_path, summary_path, factor, scale_gb):
    groups = defaultdict(list)
    with metrics_path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            if row["factor"] == factor and row["scale_gb"] == str(scale_gb):
                groups[row["query"]].append(row)

    with summary_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for query, rows in sorted(groups.items()):
            measured = [row for row in rows if int(row["iteration"]) > 0]
            warmup_failures = [
                row for row in rows
                if int(row["iteration"]) == 0 and row["status"] != "WORKING"
            ]
            successful = [row for row in measured if row["status"] == "WORKING"]
            elapsed = [float(row["elapsed_seconds"]) for row in successful if row["elapsed_seconds"]]
            user_cpu = [float(row["user_cpu_seconds"]) for row in successful if row["user_cpu_seconds"]]
            system_cpu = [float(row["system_cpu_seconds"]) for row in successful if row["system_cpu_seconds"]]
            rss = [int(row["max_rss_kb"]) for row in successful if row["max_rss_kb"]]
            writer.writerow(
                {
                    "factor": factor,
                    "scale_gb": scale_gb,
                    "query": query,
                    "warmup_runs": WARMUP_RUNS_FOR_SUMMARY,
                    "warmup_failures": len(warmup_failures),
                    "runs": len(measured),
                    "working": sum(row["status"] == "WORKING" for row in measured),
                    "failed": sum(row["status"] == "FAILED" for row in measured),
                    "timeouts": sum(row["status"] == "TIMEOUT" for row in measured),
                    "median_elapsed_seconds": f"{statistics.median(elapsed):.3f}" if elapsed else "",
                    "mean_elapsed_seconds": f"{statistics.mean(elapsed):.3f}" if elapsed else "",
                    "mean_user_cpu_seconds": f"{statistics.mean(user_cpu):.3f}" if user_cpu else "",
                    "mean_system_cpu_seconds": f"{statistics.mean(system_cpu):.3f}" if system_cpu else "",
                    "max_rss_kb": max(rss) if rss else "",
                }
            )


def main():
    global WARMUP_RUNS_FOR_SUMMARY
    args = parse_args()
    root = args.root.resolve()
    query_root = root / "queries"
    legacy_query_dir = query_root / "all_templates"

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = root / "results" / "benchmark_runs" / run_id
    log_root = run_dir / "logs"
    summary_root = run_dir / "summaries"
    run_dir.mkdir(parents=True)
    log_root.mkdir()
    summary_root.mkdir()
    metrics_path = run_dir / "query_metrics.csv"
    metadata_path = run_dir / "metadata.txt"
    duckdb_version = subprocess.run(
        [args.duckdb_bin, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    metadata_path.write_text(
        "\n".join(
            [
                f"Run ID: {run_id}",
                f"Started: {datetime.now(timezone.utc).isoformat()}",
                f"Reference scale: {args.reference_scale_gb:g} GB",
                f"Factors: {' '.join(args.factors)}",
                f"Repeats per query: {args.repeats}",
                f"Warmup runs per query: {args.warmup_runs}",
                "Execution order: complete warmup passes, then complete measured passes; queries are in ascending order.",
                "After a session restart, queries are warmed in the restarted session before measurement.",
                "Warmup and measured executions share one DuckDB process per scale unless it must be restarted.",
                f"Timeout per execution: {args.timeout_seconds} seconds",
                f"DuckDB: {duckdb_version}",
                f"Platform: {sys.platform}",
                f"CPU count: {os.cpu_count()}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    WARMUP_RUNS_FOR_SUMMARY = args.warmup_runs

    with metrics_path.open("w", newline="", encoding="utf-8") as metrics_file:
        writer = csv.DictWriter(metrics_file, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        metrics_file.flush()

        for factor_input in args.factors:
            try:
                factor_value, scale_gb = factor_scale(factor_input, args.reference_scale_gb)
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

            query_dir = query_root / tag
            if not query_dir.is_dir():
                query_dir = legacy_query_dir
            query_files = sorted(
                (
                    path
                    for path in query_dir.glob("query*.sql")
                    if re.fullmatch(r"query\d+\.sql", path.name, re.IGNORECASE)
                ),
                key=lambda path: int(re.search(r"\d+", path.stem).group()),
            )
            if not query_files:
                raise SystemExit(
                    f"ERROR: No query*.sql files found under {query_dir}. "
                    "Run scripts/01_generate_queries.sh first."
                )

            scale_log_dir = log_root / tag
            scale_log_dir.mkdir()
            database_bytes = database.stat().st_size
            print(
                f"Benchmarking factor {factor} ({scale_gb} GB, {tag}) "
                "with one persistent DuckDB process"
            )
            session = None
            query_runs = [
                (
                    query_file,
                    query_file.stem,
                    query_file.read_text(encoding="utf-8"),
                    scale_log_dir / f"{query_file.stem}.log",
                )
                for query_file in query_files
            ]
            warmup_failures = set()
            warmed_queries = set()

            def warm_query(query_run, warmup_number, phase):
                nonlocal session, warmed_queries
                query_file, query, query_sql, log_path = query_run
                try:
                    if session is None:
                        warmed_queries.clear()
                        session = DuckDBSession(
                            args.duckdb_bin, database, args.timeout_seconds
                        )
                    result = session.execute(query_sql)
                    if result["status"] != "WORKING":
                        result["error_summary"] = (
                            f"{phase} warmup {warmup_number} failed: "
                            f"{result['error_summary']}"
                        )
                        write_metric(
                            writer, run_id, factor, scale_gb, query, 0, result,
                            database_bytes, query_file, log_path
                        )
                        metrics_file.flush()
                        print(
                            f"  {tag} {query} {phase} warmup "
                            f"{warmup_number}: FAILED"
                        )
                        return False
                    warmed_queries.add(query)
                except QueryTimeout:
                    if session is not None:
                        session.terminate()
                        session = None
                    warmed_queries.clear()
                    result = {
                        "status": "TIMEOUT",
                        "elapsed_seconds": str(args.timeout_seconds),
                        "error_summary": (
                            f"{phase} warmup {warmup_number} exceeded "
                            f"{args.timeout_seconds} seconds"
                        ),
                        "exit_code": 124,
                    }
                    write_metric(
                        writer, run_id, factor, scale_gb, query, 0, result,
                        database_bytes, query_file, log_path
                    )
                    metrics_file.flush()
                    print(
                        f"  {tag} {query} {phase} warmup "
                        f"{warmup_number}: TIMEOUT"
                    )
                    return False
                except (SessionEnded, OSError) as error:
                    if session is not None:
                        session.terminate()
                        session = None
                    warmed_queries.clear()
                    result = {
                        "status": "FAILED",
                        "error_summary": f"{phase} warmup failed: {error}",
                        "exit_code": 1,
                    }
                    write_metric(
                        writer, run_id, factor, scale_gb, query, 0, result,
                        database_bytes, query_file, log_path
                    )
                    metrics_file.flush()
                    print(
                        f"  {tag} {query} {phase} warmup "
                        f"{warmup_number}: FAILED"
                    )
                    return False
                return True

            try:
                for warmup_round in range(1, args.warmup_runs + 1):
                    print(
                        f"  {tag} warmup round "
                        f"{warmup_round}/{args.warmup_runs}"
                    )
                    for query_run in query_runs:
                        query = query_run[1]
                        if query in warmup_failures:
                            continue
                        if not warm_query(query_run, warmup_round, "initial"):
                            warmup_failures.add(query)

                for iteration in range(1, args.repeats + 1):
                    print(
                        f"  {tag} measured round {iteration}/{args.repeats}"
                    )
                    for query_run in query_runs:
                        query_file, query, query_sql, log_path = query_run
                        if query in warmup_failures:
                            continue

                        if args.warmup_runs and query not in warmed_queries:
                            warmed = True
                            for warmup in range(1, args.warmup_runs + 1):
                                if not warm_query(query_run, warmup, "restart"):
                                    warmed = False
                                    warmup_failures.add(query)
                                    break
                            if not warmed:
                                continue
                        elif session is None:
                            try:
                                session = DuckDBSession(
                                    args.duckdb_bin,
                                    database,
                                    args.timeout_seconds,
                                )
                            except (SessionEnded, OSError) as error:
                                result = {
                                    "status": "FAILED",
                                    "error_summary": str(error),
                                    "exit_code": 1,
                                }
                                write_metric(
                                    writer, run_id, factor, scale_gb, query,
                                    iteration, result, database_bytes,
                                    query_file, log_path
                                )
                                metrics_file.flush()
                                print(
                                    f"  {tag} {query} run {iteration}: FAILED"
                                )
                                continue
                        try:
                            with log_path.open("a", encoding="utf-8") as log_file:
                                result = session.execute(query_sql, log_file)
                        except QueryTimeout:
                            if session is not None:
                                session.terminate()
                                session = None
                            warmed_queries.clear()
                            result = {
                                "status": "TIMEOUT",
                                "elapsed_seconds": str(args.timeout_seconds),
                                "error_summary": (
                                    f"Exceeded {args.timeout_seconds} seconds"
                                ),
                                "exit_code": 124,
                            }
                        except (SessionEnded, OSError) as error:
                            if session is not None:
                                session.terminate()
                                session = None
                            warmed_queries.clear()
                            result = {
                                "status": "FAILED",
                                "error_summary": str(error),
                                "exit_code": 1,
                            }

                        write_metric(
                            writer, run_id, factor, scale_gb, query, iteration,
                            result, database_bytes, query_file, log_path
                        )
                        metrics_file.flush()
                        print(
                            f"  {tag} {query} run {iteration}: "
                            f"{result['status']} "
                            f"{result.get('elapsed_seconds', '')} seconds"
                        )
            finally:
                if session is not None:
                    session.close()

            summary_path = summary_root / f"query_summary_{tag}.csv"
            summarize(metrics_path, summary_path, factor, scale_gb)
            print(f"Scale summary: {summary_path}")

    print(f"Raw metrics: {metrics_path}")
    print(f"Metadata: {metadata_path}")


if __name__ == "__main__":
    main()
