#!/usr/bin/env python3
"""Compatibility entry point that delegates Q74 runs to the universal runner."""

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENTS = Path(__file__).resolve().parent
UNIVERSAL_RUNNER = ROOT / "Experiments" / "run_benchmark.py"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Q74 comparison through the universal experiment benchmark."
    )
    parser.add_argument("--scale-gb", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--runtime", choices=("docker", "native"), default="docker")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.scale_gb <= 0 or args.warmups < 0 or args.repeats <= 0:
        parser.error("scale/repeats must be positive and warmups cannot be negative")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    command = [
        sys.executable,
        str(UNIVERSAL_RUNNER),
        "--baseline",
        str(EXPERIMENTS / "q74_nochanges.sql"),
        "--experiment",
        str(EXPERIMENTS / "q74_experiment1.sql"),
        "--name",
        "q74",
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
    ]
    if args.output_dir:
        command.extend(["--output-dir", str(args.output_dir.expanduser().resolve())])
    try:
        return subprocess.run(command, cwd=ROOT, check=False).returncode
    except OSError as error:
        raise SystemExit(f"Could not start universal benchmark runner: {error}") from error


if __name__ == "__main__":
    sys.exit(main())
