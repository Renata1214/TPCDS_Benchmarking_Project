#!/usr/bin/env python3
"""Run a correctness-checked benchmark for any experiment SQL pair."""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).resolve().with_name("benchmark_runner.py")
OPTIMIZER_WRAPPER = re.compile(
    r"\A\s*(?:--[^\r\n]*(?:\r?\n|$)\s*)*"
    r"SET\s+disabled_optimizers\s*=\s*'(?P<setting>[^']*)'\s*;\s*"
    r"(?:EXPLAIN\s+ANALYZE\s+)?(?P<query>.*?)\s*"
    r"SET\s+disabled_optimizers\s*=\s*''\s*;\s*\Z",
    re.IGNORECASE | re.DOTALL,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two SQL files using a result-multiset check, warm-ups, "
            "and alternating timed rounds."
        )
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument(
        "--experiment",
        required=True,
        type=Path,
        help="Experiment SQL file; EXPLAIN ANALYZE is stripped for benchmark timing.",
    )
    parser.add_argument("--name", help="Short experiment name used in output filenames.")
    parser.add_argument("--scale-gb", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument(
        "--runtime",
        choices=("docker", "native"),
        default="docker",
        help="Use the project Docker image or a local DuckDB CLI.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional new run directory. Defaults to a timestamped folder beside the baseline.",
    )
    args = parser.parse_args()
    if args.scale_gb <= 0 or args.warmups < 0 or args.repeats <= 0:
        parser.error("scale/repeats must be positive and warmups cannot be negative")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def read_optimizer_experiment(path: Path) -> Optional[Tuple[str, str]]:
    try:
        sql = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"Could not read experiment SQL {path}: {error}") from error
    match = OPTIMIZER_WRAPPER.fullmatch(sql)
    if match:
        query = match.group("query").strip().rstrip(";")
        if not query:
            raise SystemExit(f"No query found in optimizer-wrapped SQL: {path}")
        return match.group("setting"), query
    if re.search(r"\bSET\s+disabled_optimizers\b", sql, re.IGNORECASE):
        raise SystemExit(
            f"{path} changes disabled_optimizers but does not use the supported "
            "SET / query / SET disabled_optimizers = ''; structure."
        )
    return None


def main() -> int:
    args = parse_args()
    baseline = args.baseline.expanduser().resolve()
    experiment = args.experiment.expanduser().resolve()
    for path in (baseline, experiment, RUNNER):
        if not path.is_file():
            raise SystemExit(f"Required file does not exist: {path}")

    name = args.name or baseline.parent.name.lower().replace("experiments_", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise SystemExit("--name may contain only letters, numbers, _ and -")

    run_id = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else baseline.parent / f"results_{name}_{run_id}"
    )
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise SystemExit(f"Run directory already exists; refusing to overwrite: {run_dir}") from error
    except OSError as error:
        raise SystemExit(f"Could not create run directory {run_dir}: {error}") from error

    optimizer = read_optimizer_experiment(experiment)
    benchmark_experiment = experiment
    if optimizer:
        setting, query = optimizer
        benchmark_experiment = run_dir / f"{name}_experiment_benchmark.sql"
        benchmark_experiment.write_text(
            f"SET disabled_optimizers = '{setting}';\n\n"
            f"{query};\n\n"
            "SET disabled_optimizers = '';\n",
            encoding="utf-8",
        )
    else:
        setting = ""

    benchmark_output = run_dir / "benchmark"
    command = [
        sys.executable,
        str(RUNNER),
        "--baseline",
        str(baseline),
        "--optimized",
        str(benchmark_experiment),
        "--experiment-name",
        name,
        "--scale-gb",
        str(args.scale_gb),
        "--warmups",
        str(args.warmups),
        "--repeats",
        str(args.repeats),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--runtime",
        args.runtime,
        "--output-dir",
        str(benchmark_output),
    ]
    metadata = [
        f"Run ID: {run_id}",
        f"Scale: SF{args.scale_gb}",
        f"Baseline SQL: {baseline}",
        f"Experiment SQL: {experiment}",
        f"Prepared experiment SQL: {benchmark_experiment}",
        f"Disabled optimizers for experiment: {setting or '(none)'}",
        "Optimizer setting is restored to empty after each experiment query."
        if setting
        else "Experiment SQL does not alter disabled_optimizers.",
        f"Warm-up executions per version: {args.warmups}",
        f"Measured executions per version: {args.repeats}",
        f"Timeout seconds: {args.timeout_seconds}",
        f"Runtime: {args.runtime}",
        f"Benchmark command: {' '.join(command)}",
    ]
    try:
        (run_dir / "run_metadata.txt").write_text(
            "\n".join(metadata) + "\n", encoding="utf-8"
        )
    except OSError as error:
        raise SystemExit(f"Could not write run metadata: {error}") from error

    print(f"Prepared experiment SQL: {benchmark_experiment}", flush=True)
    print(f"Benchmark outputs: {benchmark_output}", flush=True)
    print(
        "The runner will compare result multisets, then warm both versions and "
        "measure in alternating order.",
        flush=True,
    )
    try:
        result = subprocess.run(command, cwd=ROOT, check=False)
    except OSError as error:
        raise SystemExit(f"Could not start benchmark engine: {error}") from error
    if result.returncode:
        raise SystemExit(
            f"Benchmark failed with exit code {result.returncode}; inspect {run_dir}"
        )
    print(f"Benchmark completed: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
