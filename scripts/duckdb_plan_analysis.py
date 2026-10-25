#!/usr/bin/env python3
"""Parse DuckDB text EXPLAIN plans into conservative operator-level summaries.

The parser is intentionally conservative: it extracts operator names and any
reliable row-count/timing observations from text plans, but it never invents
metrics between operators or across statement boundaries. Files that cannot be
parsed reliably are reported as partial or failed instead of being silently
ignored.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


OPERATOR_LINE = re.compile(r"^\s*│\s*(?P<name>[A-Z][A-Z0-9_:/\- ]*?)\s*│\s*$")
CARDINALITY_RE = re.compile(r"(?P<count>~?\s*\d[\d,]*(?:\.\d+)?)\s*rows?", re.IGNORECASE)
TIMING_RE = re.compile(r"\((?P<seconds>\d+(?:\.\d+)?)s\)", re.IGNORECASE)
TOTAL_TIME_RE = re.compile(r"Total Time:\s*(?P<seconds>\d+(?:\.\d+)?)s", re.IGNORECASE)
QUERY_NAME_RE = re.compile(r"query(?P<query>\d+)", re.IGNORECASE)
SCALE_RE = re.compile(r"sf(?P<scale>\d+)", re.IGNORECASE)
NON_OPERATOR_NAMES = {
    "AGGREGATES",
    "ANTI",
    "ASC",
    "BY",
    "CONDITIONS",
    "CROSS",
    "DESC",
    "EXPLAIN_ANALYZE",
    "FULL",
    "GROUPS",
    "INDEX",
    "INNER",
    "IS",
    "LEFT",
    "NAME",
    "NOT",
    "ORDER",
    "OUTER",
    "QUERY",
    "RIGHT",
    "SEMI",
    "TABLE",
    "TYPE",
}


def normalized_operator_name(raw_name: str) -> str:
    cleaned = raw_name.strip()
    cleaned = cleaned.replace("\u2502", "|")
    cleaned = " ".join(cleaned.split())
    return cleaned


def is_likely_operator_name(name: str) -> bool:
    if not name:
        return False
    upper = name.upper()
    if upper in NON_OPERATOR_NAMES:
        return False
    if any(token in upper for token in ("ORDER BY", "JOIN TYPE", "CTE NAME", "TABLE INDEX", "IS NOT")):
        return False
    if any(char.islower() for char in name):
        return False
    if " " in name:
        return False
    if len(name) < 3:
        return False
    if not re.fullmatch(r"[A-Z0-9_:/\-]+", name):
        return False
    return True


def parse_total_time(text: str) -> Optional[float]:
    match = TOTAL_TIME_RE.search(text)
    if match is None:
        return None
    try:
        return float(match.group("seconds"))
    except ValueError:
        return None


def extract_text_metric(text: str, regex: re.Pattern[str]) -> Optional[str]:
    match = regex.search(text)
    if match is None:
        return None
    return match.group(0).strip()


def find_operator_records(lines: List[str]) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for index, line in enumerate(lines):
        match = OPERATOR_LINE.match(line)
        if match is None:
            continue
        name = normalized_operator_name(match.group("name"))
        if not is_likely_operator_name(name):
            continue
        window = "\n".join(lines[index + 1 : min(index + 12, len(lines))])
        actual_count = None
        estimated_count = None
        timing = None
        for metric_match in CARDINALITY_RE.finditer(window):
            value = metric_match.group("count").replace("~", "").replace(",", "").strip()
            try:
                numeric = float(value)
            except ValueError:
                continue
            if metric_match.group("count").strip().startswith("~"):
                estimated_count = numeric
            else:
                if actual_count is None:
                    actual_count = numeric
        timing_match = TIMING_RE.search(window)
        if timing_match is not None:
            try:
                timing = float(timing_match.group("seconds"))
            except ValueError:
                timing = None
        if actual_count is None and estimated_count is None and timing is None:
            confidence = "low"
        elif actual_count is not None or estimated_count is not None or timing is not None:
            confidence = "medium"
            if timing is not None and (actual_count is not None or estimated_count is not None):
                confidence = "high"
        else:
            confidence = "low"
        records.append(
            {
                "operator_name": name,
                "estimated_rows": estimated_count,
                "actual_rows": actual_count,
                "time_seconds": timing,
                "confidence": confidence,
                "context": window.strip(),
            }
        )
    return records


def identify_file_kind(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".explain_analyze.txt"):
        return "EXPLAIN ANALYZE"
    if name.endswith(".explain.txt"):
        return "EXPLAIN"
    if name.startswith("combined_explain_analyze"):
        return "EXPLAIN ANALYZE"
    if name.startswith("combined_explain"):
        return "EXPLAIN"
    return "UNKNOWN"


def parse_plan_file(path: Path) -> Dict[str, object]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    total_time = parse_total_time(text)
    operator_records = find_operator_records(lines)
    file_kind = identify_file_kind(path)
    file_query_match = QUERY_NAME_RE.search(path.name)
    scale_match = SCALE_RE.search(str(path.parent))
    parse_status = "parsed"
    if not operator_records:
        parse_status = "partial"
    if total_time is None and not operator_records:
        parse_status = "failed"
    info = {
        "file": str(path),
        "scale": f"sf{scale_match.group('scale')}" if scale_match else "unknown",
        "query": f"query{file_query_match.group('query')}" if file_query_match else "unknown",
        "mode": file_kind,
        "status": parse_status,
        "total_time_seconds": total_time,
        "operator_count": len(operator_records),
        "operators_with_time": sum(1 for record in operator_records if record["time_seconds"] is not None),
        "operators_with_rows": sum(
            1 for record in operator_records if record["actual_rows"] is not None or record["estimated_rows"] is not None
        ),
        "operators_missing_metrics": sum(
            1 for record in operator_records if record["time_seconds"] is None and record["actual_rows"] is None and record["estimated_rows"] is None
        ),
        "operators": operator_records,
    }
    return info


def discover_plan_files(run_dir: Path) -> List[Path]:
    files: List[Path] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith(".explain.txt") or lower.endswith(".explain_analyze.txt"):
            files.append(path)
    return files


def build_diagnostics(plan_files: Iterable[Path]) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    file_rows: List[Dict[str, object]] = []
    operator_rows: List[Dict[str, object]] = []
    grouped_by_query: Dict[Tuple[str, str], List[Dict[str, object]]] = defaultdict(list)

    for plan_file in plan_files:
        parsed = parse_plan_file(plan_file)
        file_rows.append(
            {
                "file": parsed["file"],
                "scale": parsed["scale"],
                "query": parsed["query"],
                "mode": parsed["mode"],
                "status": parsed["status"],
                "total_time_seconds": parsed["total_time_seconds"],
                "operator_count": parsed["operator_count"],
                "operators_with_time": parsed["operators_with_time"],
                "operators_with_rows": parsed["operators_with_rows"],
                "operators_missing_metrics": parsed["operators_missing_metrics"],
            }
        )
        for record in parsed["operators"]:
            operator_entry = {
                "file": parsed["file"],
                "scale": parsed["scale"],
                "query": parsed["query"],
                "mode": parsed["mode"],
                "operator_name": record["operator_name"],
                "estimated_rows": record["estimated_rows"],
                "actual_rows": record["actual_rows"],
                "time_seconds": record["time_seconds"],
                "confidence": record["confidence"],
            }
            operator_rows.append(operator_entry)
            grouped_by_query[(parsed["scale"], parsed["query"])].append(operator_entry)

    file_rows.sort(key=lambda row: (row["scale"], row["query"], row["mode"], row["file"]))
    operator_rows.sort(key=lambda row: (row["scale"], row["query"], row["mode"], row["operator_name"], row["file"]))

    for (scale, query), entries in grouped_by_query.items():
        explanation_names = {entry["operator_name"] for entry in entries if entry["mode"] == "EXPLAIN"}
        analysis_names = {entry["operator_name"] for entry in entries if entry["mode"] == "EXPLAIN ANALYZE"}
        matched = sorted(explanation_names & analysis_names)
        unmatched = sorted((explanation_names | analysis_names) - (explanation_names & analysis_names))
        for entry in entries:
            entry["matched_operator_names"] = matched
            entry["unmatched_operator_names"] = unmatched

    return file_rows, operator_rows


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse DuckDB EXPLAIN and EXPLAIN ANALYZE text output into conservative operator summaries."
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="A results/explain_runs/<timestamp> directory or any folder containing explain files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated analysis files (default: run_dir/plan_analysis).",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory does not exist: {run_dir}")

    plan_files = discover_plan_files(run_dir)
    if not plan_files:
        raise SystemExit(f"No DuckDB EXPLAIN files found under {run_dir}")

    output_dir = args.output_dir.resolve() if args.output_dir else run_dir / "plan_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    file_rows, operator_rows = build_diagnostics(plan_files)
    write_csv(
        output_dir / "plan_file_diagnostics.csv",
        [
            "file",
            "scale",
            "query",
            "mode",
            "status",
            "total_time_seconds",
            "operator_count",
            "operators_with_time",
            "operators_with_rows",
            "operators_missing_metrics",
        ],
        file_rows,
    )
    write_csv(
        output_dir / "plan_operator_summary.csv",
        [
            "file",
            "scale",
            "query",
            "mode",
            "operator_name",
            "estimated_rows",
            "actual_rows",
            "time_seconds",
            "confidence",
            "matched_operator_names",
            "unmatched_operator_names",
        ],
        operator_rows,
    )

    # Save a machine-readable summary for downstream scripts and notebooks.
    summary = {
        "run_dir": str(run_dir),
        "files_discovered": len(plan_files),
        "files_successfully_parsed": sum(1 for row in file_rows if row["status"] == "parsed"),
        "files_partially_parsed": sum(1 for row in file_rows if row["status"] == "partial"),
        "files_failed": sum(1 for row in file_rows if row["status"] == "failed"),
        "operators_extracted": len(operator_rows),
        "operators_with_missing_metrics": sum(1 for row in operator_rows if row["time_seconds"] is None and row["actual_rows"] is None and row["estimated_rows"] is None),
    }
    (output_dir / "plan_analysis_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Discovered {len(plan_files)} explain files under {run_dir}")
    print(f"Parsed {summary['files_successfully_parsed']} files successfully")
    print(f"Partially parsed {summary['files_partially_parsed']} files")
    print(f"Failed {summary['files_failed']} files")
    print(f"Wrote outputs to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
