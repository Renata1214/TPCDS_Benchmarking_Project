import argparse
import csv
import math
import statistics
import time
from collections import Counter
from pathlib import Path

import duckdb


def read_statements(path):
    text = path.read_text(encoding="utf-8-sig")
    lines = [
        line for line in text.splitlines()
        if not line.lstrip().startswith("--")
    ]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def values_equal(a, b, atol=1e-9, rtol=1e-9):
    if a is None or b is None:
        return a is b

    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b

    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=rtol, abs_tol=atol)

    return type(a) is type(b) and a == b


def rows_equal(a, b):
    return len(a) == len(b) and all(
        values_equal(x, y) for x, y in zip(a, b)
    )


def compare_rows(left, right):
    if len(left) != len(right):
        return False, f"row count differs: original={len(left)}, optimized={len(right)}"

    unmatched = list(right)

    for row in left:
        match_index = next(
            (i for i, candidate in enumerate(unmatched)
             if rows_equal(row, candidate)),
            None,
        )
        if match_index is None:
            return False, "at least one result row has no matching row within tolerance"
        unmatched.pop(match_index)

    return True, f"{len(left)} rows match within tolerance"


def run_all(connection, statements):
    results = []
    for statement in statements:
        results.append(connection.execute(statement).fetchall())
    return results


def timed_run(connection, statements):
    start = time.perf_counter()
    run_all(connection, statements)
    return time.perf_counter() - start


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--orig-dir", default="queries/optimization/original")
    parser.add_argument("--opt-dir", default="queries/optimization/optimized")
    parser.add_argument("--db-dir", default="duckdb")
    parser.add_argument("--scales", nargs="+", type=int, default=[1, 2, 4, 8])
    parser.add_argument("--queries", nargs="+", type=int, default=[23, 39, 59, 95])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--out", default="reports/optimization/four_queries_final.csv")
    args = parser.parse_args()

    if args.repeats < 1 or args.warmups < 0:
        parser.error("--repeats must be at least 1 and --warmups cannot be negative")

    orig_dir = Path(args.orig_dir)
    opt_dir = Path(args.opt_dir)
    db_dir = Path(args.db_dir)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)

    records = []
    environment = {"duckdb_python_version": duckdb.__version__}

    print(f"DuckDB Python version: {duckdb.__version__}", flush=True)
    print(f"Scales: {args.scales}; queries: {args.queries}", flush=True)
    print(f"Warm-ups per version: {args.warmups}; measured repetitions: {args.repeats}", flush=True)

    for sf in args.scales:
        db_path = db_dir / f"tpcds_sf{sf}.duckdb"

        if not db_path.exists():
            print(f"Missing database: {db_path}", flush=True)
            for q in args.queries:
                records.append({
                    **environment,
                    "scale_factor": sf, "query": q,
                    "status": "MISSING_DATABASE",
                })
            continue

        for q in args.queries:
            orig_path = orig_dir / f"sf{sf}" / f"query{q}.sql"
            opt_path = opt_dir / f"sf{sf}" / f"query{q}.sql"
            if not orig_path.is_file():
                orig_path = orig_dir / f"query{q}.sql"
            if not opt_path.is_file():
                opt_path = opt_dir / f"query{q}.sql"
            base = {**environment, "scale_factor": sf, "query": q}

            if not orig_path.exists() or not opt_path.exists():
                print(f"SF{sf} Q{q}: SQL file missing", flush=True)
                records.append({**base, "status": "MISSING_SQL"})
                continue

            original = read_statements(orig_path)
            optimized = read_statements(opt_path)

            if len(original) != len(optimized):
                detail = (
                    f"statement count differs: original={len(original)}, "
                    f"optimized={len(optimized)}"
                )
                print(f"SF{sf} Q{q}: FAIL — {detail}", flush=True)
                records.append({
                    **base, "status": "STATEMENT_COUNT_MISMATCH",
                    "original_statements": len(original),
                    "optimized_statements": len(optimized),
                    "results_match": False,
                    "validation_detail": detail,
                })
                continue

            try:
                with duckdb.connect(str(db_path), read_only=True) as connection:
                    original_results = run_all(connection, original)
                    optimized_results = run_all(connection, optimized)

                    validations = []
                    for index, (left, right) in enumerate(
                        zip(original_results, optimized_results), start=1
                    ):
                        ok, detail = compare_rows(left, right)
                        validations.append((ok, f"statement {index}: {detail}"))

                    results_match = all(ok for ok, _ in validations)
                    validation_detail = "; ".join(detail for _, detail in validations)

                    if not results_match:
                        print(
                            f"SF{sf} Q{q}: RESULT MISMATCH — {validation_detail}",
                            flush=True,
                        )
                        records.append({
                            **base, "status": "RESULT_MISMATCH",
                            "original_statements": len(original),
                            "optimized_statements": len(optimized),
                            "results_match": False,
                            "validation_detail": validation_detail,
                        })
                        continue

                    for _ in range(args.warmups):
                        timed_run(connection, original)
                        timed_run(connection, optimized)

                    original_times = []
                    optimized_times = []

                    for repetition in range(args.repeats):
                        if repetition % 2 == 0:
                            original_times.append(timed_run(connection, original))
                            optimized_times.append(timed_run(connection, optimized))
                        else:
                            optimized_times.append(timed_run(connection, optimized))
                            original_times.append(timed_run(connection, original))

                original_median = statistics.median(original_times)
                optimized_median = statistics.median(optimized_times)
                speedup = (
                    original_median / optimized_median
                    if optimized_median > 0 else None
                )

                record = {
                    **base,
                    "status": "OK",
                    "original_statements": len(original),
                    "optimized_statements": len(optimized),
                    "warmups_per_version": args.warmups,
                    "measured_repetitions": args.repeats,
                    "original_median_s": f"{original_median:.6f}",
                    "optimized_median_s": f"{optimized_median:.6f}",
                    "speedup": f"{speedup:.3f}" if speedup is not None else "",
                    "original_runs_s": ";".join(f"{x:.6f}" for x in original_times),
                    "optimized_runs_s": ";".join(f"{x:.6f}" for x in optimized_times),
                    "results_match": True,
                    "validation_detail": validation_detail,
                }
                records.append(record)

                print(
                    f"SF{sf} Q{q}: PASS | original={original_median:.4f}s "
                    f"| optimized={optimized_median:.4f}s "
                    f"| speedup={speedup:.2f}x",
                    flush=True,
                )

            except Exception as exc:
                print(f"SF{sf} Q{q}: ERROR — {exc}", flush=True)
                records.append({
                    **base, "status": "ERROR",
                    "results_match": False,
                    "validation_detail": str(exc),
                })

    columns = [
        "duckdb_python_version",
        "scale_factor", "query", "status",
        "original_statements", "optimized_statements",
        "warmups_per_version", "measured_repetitions",
        "original_median_s", "optimized_median_s", "speedup",
        "original_runs_s", "optimized_runs_s",
        "results_match", "validation_detail",
    ]

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    failures = [r for r in records if r.get("status") != "OK"]
    print(f"\nCSV saved to: {output}", flush=True)
    print(f"Successful comparisons: {len(records) - len(failures)}/{len(records)}", flush=True)

    if failures:
        print("Some comparisons failed or were skipped. Inspect the CSV before reporting results.", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
