#!/usr/bin/env python3
"""Shared benchmark engine for SQL variants."""

import argparse
import csv
import os
import re
import selectors
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
ERROR_PATTERN = re.compile(
    r"(?:Parser|Binder|Catalog|Conversion|Invalid Input|IO|Out of Memory|"
    r"Internal|Not implemented|TransactionContext|Constraint|HTTP)? Error:",
    re.IGNORECASE,
)
EXPLAIN_PREFIX = re.compile(r"^\s*EXPLAIN\s+ANALYZE\b", re.IGNORECASE)
MEASUREMENT_FIELDS = [
    "timestamp",
    "run_id",
    "scale_gb",
    "variant",
    "phase",
    "round",
    "execution_position",
    "elapsed_seconds",
    "status",
    "error",
    "sql_file",
]
SUMMARY_FIELDS = [
    "scale_gb",
    "variant",
    "warmup_runs",
    "measured_runs",
    "failed_runs",
    "median_seconds",
    "mean_seconds",
    "stdev_seconds",
    "minimum_seconds",
    "maximum_seconds",
]


class QueryTimeout(Exception):
    pass


class DuckDBSessionError(Exception):
    pass


class DuckDBSession:
    def __init__(self, command: List[str], database: str, startup_timeout: int):
        self.process = subprocess.Popen(
            command + ["-batch", "-bail", database],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = bytearray()
        self.marker_number = 0
        self._send(".mode csv")
        self._send(".headers off")
        self._send('.nullvalue "__NULL__"')
        self._send(".print __Q47_SESSION_READY__")
        self._read_until_marker(
            b"__Q47_SESSION_READY__", time.monotonic() + startup_timeout
        )

    def _send(self, command: str) -> None:
        if self.process.poll() is not None:
            raise DuckDBSessionError(
                f"DuckDB exited with code {self.process.returncode}"
            )
        try:
            self.process.stdin.write(command.encode("utf-8") + b"\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise DuckDBSessionError("Could not send input to DuckDB") from error

    def _read_until_marker(self, marker: bytes, deadline: float) -> str:
        while True:
            marker_position = self.pending.find(marker)
            if marker_position >= 0:
                output = bytes(self.pending[:marker_position])
                del self.pending[: marker_position + len(marker)]
                return output.decode("utf-8", errors="replace")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QueryTimeout()
            events = self.selector.select(min(remaining, 0.1))
            if not events:
                if self.process.poll() is not None:
                    details = self.pending.decode("utf-8", errors="replace")
                    raise DuckDBSessionError(
                        f"DuckDB exited with code {self.process.returncode}: "
                        f"{details[-2000:]!r}"
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
            if self.process.poll() is not None and marker not in self.pending:
                details = self.pending.decode("utf-8", errors="replace")
                raise DuckDBSessionError(
                    f"DuckDB exited with code {self.process.returncode}: "
                    f"{details[-2000:]!r}"
                )

    def execute(
        self,
        sql: str,
        timeout_seconds: int,
        suppress_output: bool = False,
    ) -> Tuple[str, float]:
        self.marker_number += 1
        marker = f"__Q47_END_{self.marker_number}__"
        if suppress_output:
            self._send(".output /dev/null")
        statement = sql.strip()
        if not statement.endswith(";"):
            statement += ";"
        started = time.monotonic()
        self._send(statement)
        if suppress_output:
            self._send(".output stdout")
        self._send(f".print {marker}")
        output = self._read_until_marker(
            marker.encode("ascii"), started + timeout_seconds
        )
        error = next(
            (line.strip() for line in output.splitlines() if ERROR_PATTERN.search(line)),
            "",
        )
        if error:
            raise DuckDBSessionError(error)
        return output, time.monotonic() - started

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self._send(".quit")
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

    def terminate(self) -> None:
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


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Check query variant results, warm both alternatives, and record "
            "alternating execution timings."
        )
    )
    parser.add_argument("--scale-gb", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument(
        "--optimized",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--runtime",
        choices=("docker", "native"),
        default="docker",
        help="Use the project Docker DuckDB 1.4.3 image or a DuckDB CLI on PATH.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Unique output directory (defaults to Experiments/results_<timestamp>).",
    )
    parser.add_argument(
        "--experiment-name",
        default="experiment",
        help="Name used for default output directories and result CSV files.",
    )
    args = parser.parse_args()
    if args.scale_gb <= 0 or args.warmups < 0 or args.repeats <= 0:
        parser.error("scale/repeats must be positive and warmups cannot be negative")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.experiment_name):
        parser.error("--experiment-name may contain only letters, numbers, _ and -")
    return args


def read_query(path: Path) -> str:
    sql = path.read_text(encoding="utf-8-sig").strip()
    sql = EXPLAIN_PREFIX.sub("", sql, count=1).strip()
    sql = sql.rstrip().rstrip(";").strip()
    if not sql:
        raise ValueError(f"No query SQL found in {path}")
    return sql + ";"


def docker_available() -> bool:
    executable = shutil.which("docker")
    if executable is None:
        return False
    result = subprocess.run(
        [executable, "compose", "version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def session_command(runtime: str, database_path: Path, scale_gb: int) -> Tuple[List[str], str]:
    if runtime == "docker":
        if not docker_available():
            raise SystemExit("Docker Compose is not available; use --runtime native if installed.")
        return (
            [
                shutil.which("docker") or "docker",
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
    executable = shutil.which("duckdb")
    if executable is None:
        raise SystemExit("DuckDB CLI is not on PATH; use the default --runtime docker.")
    return [executable], str(database_path)


def parse_csv_rows(output: str) -> List[Tuple[str, ...]]:
    rows = []
    for row in csv.reader(output.splitlines()):
        if row:
            rows.append(tuple(row))
    return rows


def validate_results(
    command: List[str],
    database: str,
    baseline_sql: str,
    optimized_sql: str,
    timeout_seconds: int,
) -> Dict[str, object]:
    session = DuckDBSession(command, database, min(timeout_seconds, 60))
    try:
        baseline_output, baseline_elapsed = session.execute(
            baseline_sql, timeout_seconds
        )
        optimized_output, optimized_elapsed = session.execute(
            optimized_sql, timeout_seconds
        )
    finally:
        session.close()

    baseline_rows = parse_csv_rows(baseline_output)
    optimized_rows = parse_csv_rows(optimized_output)
    baseline_counts = Counter(baseline_rows)
    optimized_counts = Counter(optimized_rows)
    baseline_only = sum((baseline_counts - optimized_counts).values())
    optimized_only = sum((optimized_counts - baseline_counts).values())
    return {
        "baseline_rows": len(baseline_rows),
        "optimized_rows": len(optimized_rows),
        "baseline_only_rows": baseline_only,
        "optimized_only_rows": optimized_only,
        "results_equal": baseline_only == 0 and optimized_only == 0,
        "validation_baseline_elapsed_seconds": f"{baseline_elapsed:.6f}",
        "validation_optimized_elapsed_seconds": f"{optimized_elapsed:.6f}",
    }


def write_measurement(
    writer,
    run_id,
    scale,
    variant,
    phase,
    round_number,
    position,
    elapsed,
    status="OK",
    error="",
    sql_file="",
):
    writer.writerow(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "scale_gb": scale,
            "variant": variant,
            "phase": phase,
            "round": round_number,
            "execution_position": position,
            "elapsed_seconds": f"{elapsed:.6f}" if elapsed is not None else "",
            "status": status,
            "error": error,
            "sql_file": sql_file,
        }
    )


def compute_summaries(measurements, scale):
    elapsed_by_variant = defaultdict(list)
    for row in measurements:
        if row["phase"] == "measured" and row["status"] == "OK":
            elapsed_by_variant[row["variant"]].append(float(row["elapsed_seconds"]))
    summaries = []
    for variant in ("baseline", "optimized"):
        values = elapsed_by_variant[variant]
        summaries.append(
            {
                "scale_gb": scale,
                "variant": variant,
                "warmup_runs": sum(
                    row["phase"] == "warmup"
                    and row["variant"] == variant
                    and row["status"] == "OK"
                    for row in measurements
                ),
                "measured_runs": len(values),
                "failed_runs": sum(
                    row["phase"] == "measured"
                    and row["variant"] == variant
                    and row["status"] != "OK"
                    for row in measurements
                ),
                "median_seconds": f"{statistics.median(values):.6f}" if values else "",
                "mean_seconds": f"{statistics.mean(values):.6f}" if values else "",
                "stdev_seconds": f"{statistics.stdev(values):.6f}"
                if len(values) > 1
                else "",
                "minimum_seconds": f"{min(values):.6f}" if values else "",
                "maximum_seconds": f"{max(values):.6f}" if values else "",
            }
        )
    return summaries, elapsed_by_variant


def main() -> int:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    baseline_path = args.baseline.resolve()
    optimized_path = args.optimized.resolve()
    if not baseline_path.is_file():
        raise SystemExit(f"Baseline SQL file does not exist: {baseline_path}")
    if not optimized_path.is_file():
        raise SystemExit(f"Optimized SQL file does not exist: {optimized_path}")

    database_path = ROOT / "duckdb" / f"tpcds_sf{args.scale_gb}.duckdb"
    if not database_path.is_file():
        raise SystemExit(f"DuckDB database does not exist: {database_path}")
    command, database_argument = session_command(
        args.runtime, database_path, args.scale_gb
    )
    baseline_sql = read_query(baseline_path)
    optimized_sql = read_query(optimized_path)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else baseline_path.parent / f"results_{args.experiment_name}_{run_id}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    version_process = subprocess.run(
        command + ["--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    duckdb_version = version_process.stdout.strip()
    try:
        validation = validate_results(
            command,
            database_argument,
            baseline_sql,
            optimized_sql,
            args.timeout_seconds,
        )
    except (DuckDBSessionError, QueryTimeout) as error:
        raise SystemExit(
            f"Could not validate query results for SF{args.scale_gb}: {error}"
        ) from error
    with (output_dir / "result_validation.csv").open(
        "w", newline="", encoding="utf-8"
    ) as target:
        writer = csv.DictWriter(target, fieldnames=list(validation))
        writer.writeheader()
        writer.writerow(validation)

    if not validation["results_equal"]:
        raise SystemExit(
            "Baseline and optimized query results differ; no performance "
            f"comparison was run. See {output_dir / 'result_validation.csv'}"
        )

    measurements = []
    try:
        session = DuckDBSession(
            command, database_argument, min(args.timeout_seconds, 60)
        )
    except (DuckDBSessionError, QueryTimeout) as error:
        raise SystemExit(
            f"Could not open the benchmark session for SF{args.scale_gb}: {error}"
        ) from error
    try:
        for warmup in range(1, args.warmups + 1):
            variants = ["baseline", "optimized"]
            if warmup % 2 == 0:
                variants.reverse()
            for position, variant in enumerate(variants, start=1):
                query = baseline_sql if variant == "baseline" else optimized_sql
                _, elapsed = session.execute(
                    query, args.timeout_seconds, suppress_output=True
                )
                measurements.append(
                    {
                        "variant": variant,
                        "phase": "warmup",
                        "round": warmup,
                        "execution_position": position,
                        "elapsed_seconds": f"{elapsed:.6f}",
                        "status": "OK",
                    }
                )

        for round_number in range(1, args.repeats + 1):
            variants = ["baseline", "optimized"]
            if round_number % 2 == 0:
                variants.reverse()
            for position, variant in enumerate(variants, start=1):
                query = baseline_sql if variant == "baseline" else optimized_sql
                _, elapsed = session.execute(
                    query, args.timeout_seconds, suppress_output=True
                )
                measurements.append(
                    {
                        "variant": variant,
                        "phase": "measured",
                        "round": round_number,
                        "execution_position": position,
                        "elapsed_seconds": f"{elapsed:.6f}",
                        "status": "OK",
                    }
                )
    except (DuckDBSessionError, QueryTimeout) as error:
        session.terminate()
        raise SystemExit(f"Benchmark stopped before completion: {error}") from error
    finally:
        session.close()

    measurements_file = output_dir / f"{args.experiment_name}_measurements.csv"
    summary_file = output_dir / f"{args.experiment_name}_summary.csv"
    with measurements_file.open(
        "w", newline="", encoding="utf-8"
    ) as target:
        writer = csv.DictWriter(target, fieldnames=MEASUREMENT_FIELDS)
        writer.writeheader()
        for row in measurements:
            write_measurement(
                writer,
                run_id,
                args.scale_gb,
                row["variant"],
                row["phase"],
                row["round"],
                row["execution_position"],
                float(row["elapsed_seconds"]),
                row["status"],
                sql_file=str(
                    baseline_path if row["variant"] == "baseline" else optimized_path
                ),
            )

    summaries, elapsed_by_variant = compute_summaries(measurements, args.scale_gb)
    with summary_file.open(
        "w", newline="", encoding="utf-8"
    ) as target:
        writer = csv.DictWriter(target, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)

    baseline_times = elapsed_by_variant["baseline"]
    optimized_times = elapsed_by_variant["optimized"]
    baseline_median = statistics.median(baseline_times)
    optimized_median = statistics.median(optimized_times)
    speedup = baseline_median / optimized_median if optimized_median else None
    paired_speedups = []
    baseline_by_round = {
        row["round"]: float(row["elapsed_seconds"])
        for row in measurements
        if row["variant"] == "baseline" and row["phase"] == "measured"
    }
    optimized_by_round = {
        row["round"]: float(row["elapsed_seconds"])
        for row in measurements
        if row["variant"] == "optimized" and row["phase"] == "measured"
    }
    for round_number in sorted(set(baseline_by_round) & set(optimized_by_round)):
        optimized_time = optimized_by_round[round_number]
        if optimized_time:
            paired_speedups.append(baseline_by_round[round_number] / optimized_time)

    metadata = [
        f"Run ID: {run_id}",
        f"Started: {started_at.isoformat()}",
        f"DuckDB: {duckdb_version}",
        f"Runtime: {args.runtime}",
        f"Database: {database_path}",
        f"Scale: {args.scale_gb} GB",
        f"Baseline SQL: {baseline_path}",
        f"Optimized SQL: {optimized_path}",
        f"Warm-up executions per variant: {args.warmups}",
        f"Measured executions per variant: {args.repeats}",
        "Order: baseline then optimized on odd rounds; optimized then baseline on even rounds.",
        "Timing: external wall-clock time for each query in one persistent DuckDB session; CLI result display suppressed.",
        "Correctness: exact multiset comparison of CSV result rows in a separate session before timing.",
        "Benchmark performance conclusions use measured-phase times only; warm-ups and correctness-validation times are excluded.",
        f"Results equivalent: {validation['results_equal']}",
        f"Baseline median seconds: {baseline_median:.6f}",
        f"Optimized median seconds: {optimized_median:.6f}",
        f"Median-based speedup (baseline / optimized): {speedup:.6f}"
        if speedup is not None
        else "Median-based speedup: unavailable",
        f"Median paired round speedup: {statistics.median(paired_speedups):.6f}"
        if paired_speedups
        else "Median paired round speedup: unavailable",
    ]
    (output_dir / "metadata.txt").write_text(
        "\n".join(metadata) + "\n", encoding="utf-8"
    )
    print(f"Results match: {validation['results_equal']}")
    print(f"Baseline median: {baseline_median:.6f} seconds")
    print(f"Optimized median: {optimized_median:.6f} seconds")
    print(
        f"Median-based speedup: {speedup:.3f}x"
        if speedup is not None
        else "Median-based speedup: unavailable"
    )
    print(f"Measurements: {measurements_file}")
    print(f"Summary: {summary_file}")
    print(f"Metadata: {output_dir / 'metadata.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
