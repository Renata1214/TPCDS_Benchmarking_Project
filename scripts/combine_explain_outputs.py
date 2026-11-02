#!/usr/bin/env python3
"""Combine per-query EXPLAIN outputs into one document for each mode and scale."""

# Example: python3 scripts/combine_explain_outputs.py results/explain_runs/<run_id>

import argparse
import re
from pathlib import Path


QUERY_OUTPUT = re.compile(r"query(\d+)\.(explain|explain_analyze)\.txt", re.IGNORECASE)
SCALE_DIRECTORY = re.compile(r"sf(\d+)", re.IGNORECASE)


def combine_mode(scale_dir, mode, output_name):
    files = []
    for path in scale_dir.iterdir():
        match = QUERY_OUTPUT.fullmatch(path.name)
        if path.is_file() and match and match.group(2).lower() == mode:
            files.append((int(match.group(1)), path))
    files.sort(key=lambda item: (item[0], item[1].name.lower()))

    if not files:
        return 0

    output_path = scale_dir / output_name
    with output_path.open("w", encoding="utf-8", newline="\n") as output:
        for index, (number, path) in enumerate(files):
            if index:
                output.write("\n\n")
            output.write(f"{'=' * 80}\nQuery {number} - {path.name}\n{'=' * 80}\n\n")
            output.write(path.read_text(encoding="utf-8-sig").rstrip())
            output.write("\n")

    print(f"  Wrote {len(files)} query outputs to {output_path}")
    return len(files)


def main():
    parser = argparse.ArgumentParser(
        description="Combine EXPLAIN and EXPLAIN ANALYZE output files by scale."
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Explain run directory, such as results/explain_runs/20261023_140001_315347",
    )
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        parser.error(f"run directory does not exist: {run_dir}")

    scale_dirs = []
    for path in run_dir.iterdir():
        match = SCALE_DIRECTORY.fullmatch(path.name)
        if path.is_dir() and match:
            scale_dirs.append((int(match.group(1)), path))
    scale_dirs.sort(key=lambda item: item[0])
    if not scale_dirs:
        parser.error(f"no sf<scale> directories found in: {run_dir}")

    for _, scale_dir in scale_dirs:
        print(f"{scale_dir.name}:")
        explain_count = combine_mode(
            scale_dir, "explain", "combined_explain.txt"
        )
        analyze_count = combine_mode(
            scale_dir, "explain_analyze", "combined_explain_analyze.txt"
        )
        if explain_count != analyze_count:
            print(
                f"  WARNING: found {explain_count} EXPLAIN and "
                f"{analyze_count} EXPLAIN ANALYZE files"
            )


if __name__ == "__main__":
    main()
