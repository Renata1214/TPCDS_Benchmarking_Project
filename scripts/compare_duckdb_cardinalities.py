#!/usr/bin/env python3
"""Compare DuckDB estimated and actual cardinalities by JSON operator-tree path."""

# Example: docker compose run --rm -T --entrypoint python3 tpcds scripts/compare_duckdb_cardinalities.py --query-ids 1 --timeout-seconds 120 1

import argparse
import csv
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SCALE_DATABASE = re.compile(r"tpcds_sf(?P<scale>\d+)\.duckdb$", re.IGNORECASE)
QUERY_FILENAME = re.compile(r"query(?P<query>\d+)\.sql$", re.IGNORECASE)
EXPLAIN_JSON_FILENAME = re.compile(
    r"query(?P<query>\d+)\.explain\.json$", re.IGNORECASE
)
PROFILE_JSON_FILENAME = re.compile(
    r"query(?P<query>\d+)\.profile\.json$", re.IGNORECASE
)
SCALE_DIRECTORY = re.compile(r"sf(?P<scale>\d+)$", re.IGNORECASE)
COMPARISON_FIELDS = [
    "scale_gb",
    "query",
    "operator_path",
    "operator_type",
    "profile_operator_type",
    "estimated_rows",
    "estimate_source",
    "profile_estimated_rows",
    "explain_estimated_rows",
    "actual_rows",
    "absolute_difference",
    "estimated_to_actual_ratio",
    "estimate_consistency",
    "comparison_status",
    "match_confidence",
    "explain_json",
    "profile_json",
]
SUMMARY_FIELDS = [
    "scale_gb",
    "query",
    "explain_status",
    "profile_status",
    "explain_nodes",
    "profile_nodes",
    "comparison_rows",
    "matched_nodes",
    "missing_estimates",
    "missing_actuals",
    "unmatched_paths",
    "operator_type_mismatches",
    "untrusted_subtrees",
    "profile_json",
    "explain_json",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Collect DuckDB JSON EXPLAIN/profile data and compare estimated "
            "with actual rows at matching operator-tree paths."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root (defaults to the parent of this script directory).",
    )
    parser.add_argument(
        "--duckdb-bin",
        default="duckdb",
        help="DuckDB CLI executable.",
    )
    parser.add_argument(
        "--reference-scale-gb",
        type=float,
        default=10,
        help="Reference scale used to record relative factors in metadata.",
    )
    parser.add_argument(
        "--warmup-rounds",
        type=int,
        default=1,
        help="Complete workload rounds before collection (default: 1).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Maximum time for any single warm-up, EXPLAIN, or profile statement.",
    )
    parser.add_argument(
        "--query-ids",
        type=int,
        nargs="+",
        help="Optional query numbers to collect (default: every discovered query).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: results/cardinality_runs/<timestamp>).",
    )
    parser.add_argument(
        "--reprocess-run",
        type=Path,
        help="Rebuild comparison CSVs from an existing run's saved JSON without rerunning queries.",
    )
    parser.add_argument(
        "scales",
        nargs="*",
        type=int,
        help="Physical scale sizes in GB; defaults to discovered DuckDB databases.",
    )
    args = parser.parse_args()
    if args.reference_scale_gb <= 0:
        parser.error("--reference-scale-gb must be greater than zero")
    if args.warmup_rounds < 0 or args.timeout_seconds <= 0:
        parser.error("warm-up rounds cannot be negative and timeout must be positive")
    return args


def discover_scales(database_dir: Path, requested_scales: List[int]) -> List[int]:
    if requested_scales:
        return sorted(set(requested_scales))
    discovered = []
    for path in database_dir.glob("tpcds_sf*.duckdb"):
        match = SCALE_DATABASE.fullmatch(path.name)
        if match:
            discovered.append(int(match.group("scale")))
    return sorted(set(discovered))


def query_files_for_scale(query_root: Path, scale_gb: int) -> Dict[int, Path]:
    selected: Dict[int, Path] = {}
    for directory in (query_root / "all_templates", query_root / f"sf{scale_gb}"):
        if not directory.is_dir():
            continue
        for path in directory.glob("query*.sql"):
            match = QUERY_FILENAME.fullmatch(path.name)
            if match and path.is_file():
                selected[int(match.group("query"))] = path
    return selected


class QueryTimeout(Exception):
    pass


class DuckDBSessionError(Exception):
    pass


class DuckDBSession:
    def __init__(self, executable: str, database: Path):
        self.process = subprocess.Popen(
            [executable, "-batch", "-bail", str(database)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.pending = bytearray()
        self.marker_counter = 0

    def _send(self, command: str) -> None:
        if self.process.poll() is not None:
            raise DuckDBSessionError(
                f"DuckDB exited with code {self.process.returncode}"
            )
        try:
            self.process.stdin.write(command.encode("utf-8") + b"\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise DuckDBSessionError("Could not send SQL to DuckDB") from error

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

    def execute(
        self,
        sql: str,
        timeout_seconds: int,
        capture_output: bool = True,
    ) -> Tuple[str, float]:
        self.marker_counter += 1
        marker = f"__TPCDS_CARDINALITY_END_{self.marker_counter}__"
        if not capture_output:
            self._send(".output /dev/null")
        started = time.monotonic()
        self._send(sql)
        if not capture_output:
            self._send(".output stdout")
        self._send(f".print {marker}")
        output = self._read_until_marker(
            marker.encode("ascii"), started + timeout_seconds
        )
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


def sql_statement(query_file: Path) -> str:
    sql = query_file.read_text(encoding="utf-8-sig").strip()
    if not sql:
        raise ValueError(f"Query file is empty: {query_file}")
    return re.sub(r";\s*$", "", sql).rstrip() + ";"


def parse_explain_json(output: str) -> List[Dict[str, object]]:
    start = output.find("[")
    if start < 0:
        raise ValueError("EXPLAIN (FORMAT JSON) output did not contain a JSON array")
    try:
        plan, _ = json.JSONDecoder().raw_decode(output[start:])
    except json.JSONDecodeError as error:
        raise ValueError(f"Could not decode EXPLAIN JSON: {error}") from error
    if not isinstance(plan, list):
        raise ValueError("EXPLAIN JSON root must be an array of operator nodes")
    return plan


def parse_cardinality(value: object) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    text = text.removeprefix("~")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_operator_name(name: object) -> str:
    normalized = str(name or "").strip().upper()
    if normalized == "SEQ_SCAN":
        return "TABLE_SCAN"
    return normalized


def flatten_plan(
    nodes: Iterable[Dict[str, object]],
    node_kind: str,
) -> Dict[str, Dict[str, object]]:
    flattened: Dict[str, Dict[str, object]] = {}

    def visit(children: Iterable[Dict[str, object]], parent_path: str) -> None:
        for index, node in enumerate(children):
            path = f"{parent_path}/{index}" if parent_path else str(index)
            if node_kind == "explain":
                operator_type = str(node.get("name") or "").strip()
                extra_info = node.get("extra_info")
                if not isinstance(extra_info, dict):
                    extra_info = {}
                estimated = parse_cardinality(extra_info.get("Estimated Cardinality"))
                actual = None
            else:
                operator_type = str(
                    node.get("operator_type") or node.get("operator_name") or ""
                ).strip()
                extra_info = node.get("extra_info")
                if not isinstance(extra_info, dict):
                    extra_info = {}
                estimated = parse_cardinality(extra_info.get("Estimated Cardinality"))
                actual = parse_cardinality(node.get("operator_cardinality"))
            flattened[path] = {
                "operator_type": operator_type,
                "estimated_rows": estimated,
                "actual_rows": actual,
            }
            descendants = node.get("children")
            if isinstance(descendants, list):
                visit(descendants, path)

    visit(nodes, "")
    return flattened


def compare_operator_trees(
    scale_gb: int,
    query: str,
    explain_nodes: Dict[str, Dict[str, object]],
    profile_nodes: Dict[str, Dict[str, object]],
    explain_path: str,
    profile_path: str,
) -> List[Dict[str, object]]:
    rows = []
    trusted_paths: Dict[str, bool] = {}
    for path in sorted(
        set(explain_nodes) | set(profile_nodes),
        key=lambda item: tuple(int(part) for part in item.split("/")),
    ):
        explain_node = explain_nodes.get(path)
        profile_node = profile_nodes.get(path)
        explain_type = (
            str(explain_node["operator_type"]) if explain_node is not None else ""
        )
        profile_type = (
            str(profile_node["operator_type"]) if profile_node is not None else ""
        )
        estimated_from_explain = (
            explain_node["estimated_rows"] if explain_node is not None else None
        )
        estimated_from_profile = (
            profile_node["estimated_rows"] if profile_node is not None else None
        )
        actual_rows = profile_node["actual_rows"] if profile_node is not None else None

        parent_path = path.rpartition("/")[0]
        parent_is_trusted = not parent_path or trusted_paths.get(parent_path, False)
        if not parent_is_trusted:
            status = "untrusted_subtree"
            confidence = "low"
            estimated_rows = None
            estimate_source = "untrusted_ancestor"
        elif explain_node is None:
            status = "unmatched_in_explain"
            confidence = "low"
            estimated_rows = None
            estimate_source = "missing"
        elif profile_node is None:
            status = "unmatched_in_profile"
            confidence = "low"
            estimated_rows = estimated_from_explain
            estimate_source = "explain_json" if estimated_rows is not None else "missing"
        else:
            same_type = normalize_operator_name(explain_type) == normalize_operator_name(
                profile_type
            )
            if not same_type:
                status = "operator_type_mismatch"
                confidence = "low"
                estimated_rows = None
                estimate_source = "untrusted_path"
            else:
                confidence = "high" if explain_type.strip().upper() == profile_type.upper() else "medium"
                if estimated_from_profile is not None:
                    estimated_rows = estimated_from_profile
                    estimate_source = "profile_extra_info"
                else:
                    estimated_rows = estimated_from_explain
                    estimate_source = (
                        "explain_json" if estimated_rows is not None else "missing"
                    )
                if estimated_rows is None and actual_rows is None:
                    status = "missing_estimate_and_actual"
                elif estimated_rows is None:
                    status = "missing_estimate"
                elif actual_rows is None:
                    status = "missing_actual"
                else:
                    status = "matched"
        trusted_paths[path] = status in (
            "matched",
            "missing_estimate",
            "missing_actual",
            "missing_estimate_and_actual",
        )

        estimate_consistency = ""
        if status in (
            "operator_type_mismatch",
            "unmatched_in_explain",
            "unmatched_in_profile",
            "untrusted_subtree",
        ):
            estimate_consistency = "not_comparable"
        elif estimated_from_profile is not None and estimated_from_explain is not None:
            estimate_consistency = (
                "same"
                if estimated_from_profile == estimated_from_explain
                else "different"
            )
        elif estimated_from_profile is None:
            estimate_consistency = "missing_profile_estimate"
        else:
            estimate_consistency = "missing_explain_estimate"

        absolute_difference = ""
        estimated_to_actual_ratio = ""
        if status in ("matched",) and estimated_rows is not None and actual_rows is not None:
            absolute_difference = abs(estimated_rows - actual_rows)
            if actual_rows != 0:
                estimated_to_actual_ratio = estimated_rows / actual_rows

        operator_type = explain_type or profile_type
        rows.append(
            {
                "scale_gb": scale_gb,
                "query": query,
                "operator_path": path,
                "operator_type": operator_type,
                "profile_operator_type": profile_type,
                "estimated_rows": estimated_rows if estimated_rows is not None else "",
                "estimate_source": estimate_source,
                "profile_estimated_rows": (
                    estimated_from_profile
                    if estimated_from_profile is not None
                    else ""
                ),
                "explain_estimated_rows": (
                    estimated_from_explain
                    if estimated_from_explain is not None
                    else ""
                ),
                "actual_rows": actual_rows if actual_rows is not None else "",
                "absolute_difference": absolute_difference,
                "estimated_to_actual_ratio": estimated_to_actual_ratio,
                "estimate_consistency": estimate_consistency,
                "comparison_status": status,
                "match_confidence": confidence,
                "explain_json": explain_path,
                "profile_json": profile_path,
            }
        )
    return rows


def write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, object]]):
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_comparisons(
    run_dir: Path,
    scales: List[int],
    version: str,
    all_comparisons: List[Dict[str, object]],
    all_queries: List[Dict[str, object]],
) -> Dict[str, object]:
    summary = {
        "run_dir": str(run_dir),
        "duckdb_version": version,
        "scales_gb": scales,
        "queries_discovered": len(all_queries),
        "explain_json_files_processed": sum(
            row["explain_status"] == "parsed" for row in all_queries
        ),
        "profile_json_files_processed": sum(
            row["profile_status"] == "parsed" for row in all_queries
        ),
        "operator_comparisons_produced": len(all_comparisons),
        "matched_nodes": sum(row["comparison_status"] == "matched" for row in all_comparisons),
        "missing_estimates": sum(
            row["comparison_status"]
            in ("missing_estimate", "missing_estimate_and_actual")
            for row in all_comparisons
        ),
        "missing_actuals": sum(
            row["comparison_status"]
            in ("missing_actual", "missing_estimate_and_actual")
            for row in all_comparisons
        ),
        "unmatched_paths": sum(
            row["comparison_status"]
            in ("unmatched_in_explain", "unmatched_in_profile")
            for row in all_comparisons
        ),
        "operator_type_mismatches": sum(
            row["comparison_status"] == "operator_type_mismatch"
            for row in all_comparisons
        ),
        "untrusted_subtrees": sum(
            row["comparison_status"] == "untrusted_subtree"
            for row in all_comparisons
        ),
        "comparison_status_counts": {
            status: sum(row["comparison_status"] == status for row in all_comparisons)
            for status in sorted({row["comparison_status"] for row in all_comparisons})
        },
    }
    return summary


def reprocess_run(run_dir: Path) -> int:
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory does not exist: {run_dir}")
    scale_dirs = []
    for path in run_dir.iterdir():
        match = SCALE_DIRECTORY.fullmatch(path.name)
        if path.is_dir() and match:
            scale_dirs.append((int(match.group("scale")), path))
    scale_dirs.sort(key=lambda item: item[0])
    if not scale_dirs:
        raise SystemExit(f"No sf<scale> directories found in {run_dir}")

    metadata_path = run_dir / "metadata.txt"
    metadata = (
        metadata_path.read_text(encoding="utf-8").splitlines()
        if metadata_path.is_file()
        else []
    )
    version = next(
        (line.partition(":")[2].strip() for line in metadata if line.startswith("DuckDB:")),
        "unknown",
    )
    scales = []
    all_comparisons = []
    all_queries = []
    for scale_gb, scale_dir in scale_dirs:
        scales.append(scale_gb)
        explain_dir = scale_dir / "json_explains"
        profile_dir = scale_dir / "json_profiles"
        explain_files = {}
        profile_files = {}
        for path in explain_dir.glob("query*.explain.json"):
            match = EXPLAIN_JSON_FILENAME.fullmatch(path.name)
            if match:
                explain_files[int(match.group("query"))] = path
        for path in profile_dir.glob("query*.profile.json"):
            match = PROFILE_JSON_FILENAME.fullmatch(path.name)
            if match:
                profile_files[int(match.group("query"))] = path
        query_ids = sorted(set(explain_files) | set(profile_files))
        scale_comparisons = []
        scale_queries = []
        for number in query_ids:
            query = f"query{number}"
            explain_path = explain_files.get(number)
            profile_path = profile_files.get(number)
            if explain_path is None or profile_path is None:
                raise SystemExit(
                    f"Missing JSON plan/profile pair for SF{scale_gb} {query}"
                )
            explain_tree = json.loads(explain_path.read_text(encoding="utf-8"))
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if not isinstance(profile, dict) or not isinstance(profile.get("children"), list):
                raise ValueError(f"Invalid JSON profile structure: {profile_path}")
            explain_nodes = flatten_plan(explain_tree, "explain")
            profile_nodes = flatten_plan(profile["children"], "profile")
            rows = compare_operator_trees(
                scale_gb,
                query,
                explain_nodes,
                profile_nodes,
                str(explain_path),
                str(profile_path),
            )
            scale_comparisons.extend(rows)
            statuses = [row["comparison_status"] for row in rows]
            scale_queries.append(
                {
                    "scale_gb": scale_gb,
                    "query": query,
                    "explain_status": "parsed",
                    "profile_status": "parsed",
                    "explain_nodes": len(explain_nodes),
                    "profile_nodes": len(profile_nodes),
                    "comparison_rows": len(rows),
                    "matched_nodes": sum(status == "matched" for status in statuses),
                    "missing_estimates": sum(
                        status in ("missing_estimate", "missing_estimate_and_actual")
                        for status in statuses
                    ),
                    "missing_actuals": sum(
                        status in ("missing_actual", "missing_estimate_and_actual")
                        for status in statuses
                    ),
                    "unmatched_paths": sum(
                        status in ("unmatched_in_explain", "unmatched_in_profile")
                        for status in statuses
                    ),
                    "operator_type_mismatches": sum(
                        status == "operator_type_mismatch" for status in statuses
                    ),
                    "untrusted_subtrees": sum(
                        status == "untrusted_subtree" for status in statuses
                    ),
                    "profile_json": str(profile_path),
                    "explain_json": str(explain_path),
                }
            )
        write_csv(
            scale_dir / "operator_cardinality_comparison.csv",
            COMPARISON_FIELDS,
            scale_comparisons,
        )
        write_csv(scale_dir / "query_summary.csv", SUMMARY_FIELDS, scale_queries)
        all_comparisons.extend(scale_comparisons)
        all_queries.extend(scale_queries)

    write_csv(
        run_dir / "operator_cardinality_comparison.csv",
        COMPARISON_FIELDS,
        all_comparisons,
    )
    write_csv(run_dir / "query_summary.csv", SUMMARY_FIELDS, all_queries)
    summary = summarize_comparisons(
        run_dir,
        scales,
        version,
        all_comparisons,
        all_queries,
    )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    replaced_prefixes = (
        "Comparison CSVs rebuilt from saved JSON:",
        "Operator comparison rows:",
        "Missing estimates:",
        "Missing actual cardinalities:",
        "Unmatched tree paths:",
        "Operator-type mismatches:",
        "Untrusted subtree rows:",
        "Operator matching:",
    )
    metadata = [
        line
        for line in metadata
        if not line.startswith(replaced_prefixes)
    ]
    metadata.extend(
        [
            "Operator matching: exact tree path, normalized operator type, and trusted ancestor chain; SEQ_SCAN and TABLE_SCAN are equivalent scan labels.",
            f"Comparison CSVs rebuilt from saved JSON: {datetime.now(timezone.utc).isoformat()}",
            f"Operator comparison rows: {summary['operator_comparisons_produced']}",
            f"Missing estimates: {summary['missing_estimates']}",
            f"Missing actual cardinalities: {summary['missing_actuals']}",
            f"Unmatched tree paths: {summary['unmatched_paths']}",
            f"Operator-type mismatches: {summary['operator_type_mismatches']}",
            f"Untrusted subtree rows: {summary['untrusted_subtrees']}",
        ]
    )
    metadata_path.write_text("\n".join(metadata) + "\n", encoding="utf-8")
    print(
        f"Rebuilt {len(all_comparisons)} operator comparisons from saved JSON "
        f"under {run_dir}"
    )
    return 0


def sql_quote(path: Path) -> str:
    return str(path).replace("'", "''")


def run_scale(
    duckdb_bin: str,
    database: Path,
    scale_gb: int,
    query_files: Dict[int, Path],
    run_dir: Path,
    timeout_seconds: int,
    warmup_rounds: int,
) -> Tuple[List[Dict[str, object]], List[Dict[str, object]], List[Dict[str, object]]]:
    scale_dir = run_dir / f"sf{scale_gb}"
    explain_dir = scale_dir / "json_explains"
    profile_dir = scale_dir / "json_profiles"
    explain_dir.mkdir(parents=True)
    profile_dir.mkdir(parents=True)

    ordered_queries = sorted(query_files.items())
    comparison_rows = []
    query_summaries = []
    warmup_rows = []
    session = DuckDBSession(duckdb_bin, database)
    try:
        for warmup_round in range(1, warmup_rounds + 1):
            for position, (number, query_file) in enumerate(ordered_queries, start=1):
                _, elapsed = session.execute(
                    sql_statement(query_file),
                    timeout_seconds,
                    capture_output=False,
                )
                warmup_rows.append(
                    {
                        "scale_gb": scale_gb,
                        "warmup_round": warmup_round,
                        "execution_position": position,
                        "query": f"query{number}",
                        "status": "completed",
                        "elapsed_seconds": f"{elapsed:.3f}",
                        "query_file": str(query_file),
                    }
                )

        for number, query_file in ordered_queries:
            query = f"query{number}"
            explain_path = explain_dir / f"{query}.explain.json"
            profile_path = profile_dir / f"{query}.profile.json"
            sql = sql_statement(query_file)
            explain_output, _ = session.execute(
                f"EXPLAIN (FORMAT JSON) {sql}",
                timeout_seconds,
            )
            explain_tree = parse_explain_json(explain_output)
            explain_path.write_text(
                json.dumps(explain_tree, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            explain_nodes = flatten_plan(explain_tree, "explain")

            session.execute("PRAGMA disable_profiling;", 30, capture_output=False)
            session.execute(
                f"SET profiling_output='{sql_quote(profile_path)}';",
                30,
                capture_output=False,
            )
            session.execute(
                "SET enable_profiling='json';",
                30,
                capture_output=False,
            )
            session.execute(sql, timeout_seconds, capture_output=False)
            session.execute("PRAGMA disable_profiling;", 30, capture_output=False)

            if not profile_path.is_file():
                raise RuntimeError(
                    f"DuckDB did not write the expected JSON profile: {profile_path}"
                )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            if not isinstance(profile, dict) or not isinstance(profile.get("children"), list):
                raise ValueError(f"Invalid JSON profile structure: {profile_path}")
            profile_nodes = flatten_plan(profile["children"], "profile")
            rows = compare_operator_trees(
                scale_gb,
                query,
                explain_nodes,
                profile_nodes,
                str(explain_path),
                str(profile_path),
            )
            comparison_rows.extend(rows)
            statuses = [row["comparison_status"] for row in rows]
            query_summaries.append(
                {
                    "scale_gb": scale_gb,
                    "query": query,
                    "explain_status": "parsed",
                    "profile_status": "parsed",
                    "explain_nodes": len(explain_nodes),
                    "profile_nodes": len(profile_nodes),
                    "comparison_rows": len(rows),
                    "matched_nodes": sum(status == "matched" for status in statuses),
                    "missing_estimates": sum(
                        status in ("missing_estimate", "missing_estimate_and_actual")
                        for status in statuses
                    ),
                    "missing_actuals": sum(
                        status in ("missing_actual", "missing_estimate_and_actual")
                        for status in statuses
                    ),
                    "unmatched_paths": sum(
                        status in ("unmatched_in_explain", "unmatched_in_profile")
                        for status in statuses
                    ),
                    "operator_type_mismatches": sum(
                        status == "operator_type_mismatch" for status in statuses
                    ),
                    "untrusted_subtrees": sum(
                        status == "untrusted_subtree" for status in statuses
                    ),
                    "profile_json": str(profile_path),
                    "explain_json": str(explain_path),
                }
            )
    finally:
        session.close()

    write_csv(
        scale_dir / "operator_cardinality_comparison.csv",
        COMPARISON_FIELDS,
        comparison_rows,
    )
    write_csv(scale_dir / "query_summary.csv", SUMMARY_FIELDS, query_summaries)
    return comparison_rows, query_summaries, warmup_rows


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if args.reprocess_run is not None:
        reprocess_dir = args.reprocess_run
        if not reprocess_dir.is_absolute():
            reprocess_dir = root / reprocess_dir
        return reprocess_run(reprocess_dir.resolve())

    duckdb_bin = shutil.which(args.duckdb_bin)
    if duckdb_bin is None:
        raise SystemExit(f"DuckDB CLI was not found: {args.duckdb_bin}")
    version = subprocess.run(
        [duckdb_bin, "--version"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    if "1.4.3" not in version:
        raise SystemExit(
            f"Expected DuckDB 1.4.3 for comparable JSON fields; found {version}"
        )

    scales = discover_scales(root / "duckdb", args.scales)
    if not scales:
        raise SystemExit(f"No DuckDB databases discovered in {root / 'duckdb'}")
    if args.output_dir is None:
        run_dir = (
            root
            / "results"
            / "cardinality_runs"
            / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        )
    else:
        run_dir = args.output_dir
        if not run_dir.is_absolute():
            run_dir = root / run_dir
    run_dir.mkdir(parents=True, exist_ok=False)

    started = datetime.now(timezone.utc)
    metadata = [
        f"Run started: {started.isoformat()}",
        f"Reference scale: {args.reference_scale_gb:g} GB",
        f"Scales (physical GB): {' '.join(str(scale) for scale in scales)}",
        f"Warm-up rounds per scale: {args.warmup_rounds}",
        "Warm-up protocol: full query passes in ascending query-number order.",
        "Collection protocol: EXPLAIN (FORMAT JSON), then JSON profiling execution per query in the same persistent DuckDB session.",
        "Profile timing and latency are diagnostic only and are not benchmark measurements.",
        f"Timeout per warm-up, EXPLAIN, and profile statement: {args.timeout_seconds} seconds.",
        f"Query selection: {'all available' if not args.query_ids else ', '.join(str(number) for number in sorted(set(args.query_ids)))}.",
        f"DuckDB: {version}",
        f"Platform: {sys.platform}",
        "Operator matching: exact tree path, normalized operator type, and trusted ancestor chain; SEQ_SCAN and TABLE_SCAN are equivalent scan labels.",
        f"Estimated cardinality source: profile operator extra_info when present, otherwise matching EXPLAIN JSON node.",
    ]
    all_comparisons = []
    all_queries = []
    all_warmups = []
    for scale_gb in scales:
        database = root / "duckdb" / f"tpcds_sf{scale_gb}.duckdb"
        if not database.is_file():
            raise SystemExit(f"Missing database: {database}")
        query_files = query_files_for_scale(root / "queries", scale_gb)
        if args.query_ids:
            requested_ids = set(args.query_ids)
            missing_ids = requested_ids.difference(query_files)
            if missing_ids:
                raise SystemExit(
                    f"SF{scale_gb} is missing requested queries: "
                    f"{', '.join(str(number) for number in sorted(missing_ids))}"
                )
            query_files = {
                number: path
                for number, path in query_files.items()
                if number in requested_ids
            }
        if not query_files:
            raise SystemExit(f"No query<number>.sql files found for SF{scale_gb}")
        print(f"SF{scale_gb}: {len(query_files)} queries")
        try:
            comparisons, summaries, warmup_rows = run_scale(
                duckdb_bin,
                database,
                scale_gb,
                query_files,
                run_dir,
                args.timeout_seconds,
                args.warmup_rounds,
            )
        except (
            DuckDBSessionError,
            OSError,
            QueryTimeout,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
            subprocess.TimeoutExpired,
        ) as error:
            metadata.append(f"SF{scale_gb} error: {error}")
            (run_dir / "metadata.txt").write_text(
                "\n".join(metadata) + "\n", encoding="utf-8"
            )
            raise SystemExit(f"SF{scale_gb} analysis failed: {error}") from error
        all_comparisons.extend(comparisons)
        all_queries.extend(summaries)
        all_warmups.extend(warmup_rows)
        print(
            f"  completed {len(summaries)} profiles, "
            f"{len(comparisons)} operator comparisons"
        )

    write_csv(
        run_dir / "operator_cardinality_comparison.csv",
        COMPARISON_FIELDS,
        all_comparisons,
    )
    write_csv(run_dir / "query_summary.csv", SUMMARY_FIELDS, all_queries)
    write_csv(
        run_dir / "warmup_results.csv",
        [
            "scale_gb",
            "warmup_round",
            "execution_position",
            "query",
            "status",
            "elapsed_seconds",
            "query_file",
        ],
        all_warmups,
    )

    summary = summarize_comparisons(
        run_dir,
        scales,
        version,
        all_comparisons,
        all_queries,
    )
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata.extend(
        [
            f"Run completed: {datetime.now(timezone.utc).isoformat()}",
            f"Queries processed: {summary['queries_discovered']}",
            f"Operator comparison rows: {summary['operator_comparisons_produced']}",
            f"Missing estimates: {summary['missing_estimates']}",
            f"Missing actual cardinalities: {summary['missing_actuals']}",
            f"Unmatched tree paths: {summary['unmatched_paths']}",
            f"Operator-type mismatches: {summary['operator_type_mismatches']}",
            f"Untrusted subtree rows: {summary['untrusted_subtrees']}",
        ]
    )
    (run_dir / "metadata.txt").write_text(
        "\n".join(metadata) + "\n", encoding="utf-8"
    )
    print(f"Comparison CSV: {run_dir / 'operator_cardinality_comparison.csv'}")
    print(f"Summary: {run_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
