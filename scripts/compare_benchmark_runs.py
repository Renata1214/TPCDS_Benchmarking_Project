#!/usr/bin/env python3
"""Compare two benchmark_runs folders with per-query tables and SVG charts."""

import argparse
import csv
import html
import math
import re
from pathlib import Path


SUMMARY_FILENAME = re.compile(r"query_summary_sf(\d+)\.csv", re.IGNORECASE)
QUERY_NUMBER = re.compile(r"query(\d+)", re.IGNORECASE)
REQUIRED_FIELDS = {
    "scale_gb",
    "query",
    "runs",
    "working",
    "failed",
    "timeouts",
    "median_elapsed_seconds",
    "mean_elapsed_seconds",
}
COLORS = ("#2563eb", "#dc2626")


def query_key(query):
    match = QUERY_NUMBER.fullmatch(query)
    if not match:
        raise ValueError(f"unexpected query name in summary: {query!r}")
    return int(match.group(1))


def load_run(run_dir):
    summary_dir = run_dir / "summaries"
    if not summary_dir.is_dir():
        raise ValueError(f"summary directory does not exist: {summary_dir}")
    summaries = {}
    for path in summary_dir.iterdir():
        match = SUMMARY_FILENAME.fullmatch(path.name)
        if not path.is_file() or not match:
            continue
        scale = int(match.group(1))
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            missing = REQUIRED_FIELDS.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(
                    f"{path} is missing required columns: "
                    f"{', '.join(sorted(missing))}"
                )
            rows = {}
            for row in reader:
                query = row["query"]
                query_key(query)
                try:
                    row_scale = int(row["scale_gb"])
                    runs = int(row["runs"])
                    working = int(row["working"])
                    failed = int(row["failed"])
                    timeouts = int(row["timeouts"])
                    median = (
                        float(row["median_elapsed_seconds"])
                        if row["median_elapsed_seconds"]
                        else None
                    )
                    mean = (
                        float(row["mean_elapsed_seconds"])
                        if row["mean_elapsed_seconds"]
                        else None
                    )
                except (TypeError, ValueError) as error:
                    raise ValueError(f"invalid summary row in {path}: {row}") from error
                if row_scale != scale:
                    raise ValueError(f"scale mismatch in {path}: SF{row_scale}")
                if query in rows:
                    raise ValueError(f"duplicate {query} row in {path}")
                for label, value in (("median", median), ("mean", mean)):
                    if value is not None and (
                        not math.isfinite(value) or value < 0
                    ):
                        raise ValueError(
                            f"invalid {label} runtime for {query} SF{scale} in {path}"
                        )
                rows[query] = {
                    "scale_gb": scale,
                    "query": query,
                    "runs": runs,
                    "working": working,
                    "failed": failed,
                    "timeouts": timeouts,
                    "median": median,
                    "mean": mean,
                }
        if not rows:
            raise ValueError(f"no query rows found in {path}")
        summaries[scale] = rows
    if not summaries:
        raise ValueError(f"no query_summary_sf<scale>.csv files found in {summary_dir}")
    return summaries


def runtime_label(run_dir):
    metadata = run_dir / "metadata.txt"
    if not metadata.is_file():
        return run_dir.name
    for line in metadata.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("Run ID:"):
            return line.split(":", 1)[1].strip()
    return run_dir.name


def comparison_rows(first, second):
    scales = sorted(set(first).intersection(second))
    if not scales:
        raise ValueError("the runs have no scale factors in common")
    rows = []
    for scale in scales:
        first_queries = first[scale]
        second_queries = second[scale]
        if set(first_queries) != set(second_queries):
            only_first = sorted(set(first_queries) - set(second_queries), key=query_key)
            only_second = sorted(set(second_queries) - set(first_queries), key=query_key)
            raise ValueError(
                f"query coverage differs at SF{scale}; "
                f"only in first run: {only_first}; only in second run: {only_second}"
            )
        for query in sorted(first_queries, key=query_key):
            old = first_queries[query]
            new = second_queries[query]
            row = {
                "scale_gb": scale,
                "query": query,
                "run1_median_seconds": old["median"],
                "run2_median_seconds": new["median"],
                "median_delta_seconds": None,
                "median_change_percent": None,
                "run1_mean_seconds": old["mean"],
                "run2_mean_seconds": new["mean"],
                "mean_delta_seconds": None,
                "mean_change_percent": None,
                "run1_working": old["working"],
                "run2_working": new["working"],
                "run1_failed": old["failed"],
                "run2_failed": new["failed"],
                "run1_timeouts": old["timeouts"],
                "run2_timeouts": new["timeouts"],
            }
            if old["median"] is not None and new["median"] is not None:
                row["median_delta_seconds"] = new["median"] - old["median"]
                if old["median"]:
                    row["median_change_percent"] = (
                        (new["median"] - old["median"]) / old["median"] * 100
                    )
            if old["mean"] is not None and new["mean"] is not None:
                row["mean_delta_seconds"] = new["mean"] - old["mean"]
                if old["mean"]:
                    row["mean_change_percent"] = (
                        (new["mean"] - old["mean"]) / old["mean"] * 100
                    )
            rows.append(row)
    return rows


def format_number(value, digits=6):
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def write_comparison_csv(path, rows):
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: format_number(value, 6)
                    if isinstance(value, float)
                    else value
                    for key, value in row.items()
                }
            )


def svg_document(title, body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="620" '
        'viewBox="0 0 1200 620" role="img" '
        f'aria-label="{html.escape(title)}">'
        "<style>text{font-family:Arial,sans-serif;fill:#1f2937}"
        ".muted{fill:#6b7280}.grid{stroke:#e5e7eb;stroke-width:1}"
        ".axis{stroke:#6b7280;stroke-width:1}</style>"
        f'<text x="30" y="34" font-size="21" font-weight="bold">'
        f"{html.escape(title)}</text>{body}</svg>"
    )


def write_scale_chart(path, scale, rows, labels):
    width, height = 1200, 620
    left, right, top, bottom = 85, 35, 75, 520
    plot_width = width - left - right
    plot_height = bottom - top
    scale_rows = [row for row in rows if row["scale_gb"] == scale]
    queries = [row["query"] for row in scale_rows]
    values = [
        row[key]
        for row in scale_rows
        for key in ("run1_median_seconds", "run2_median_seconds")
        if row[key] is not None
    ]
    if not values:
        raise ValueError(f"no successful medians to plot at SF{scale}")
    minimum = min(values)
    maximum = max(values)
    use_log = maximum / minimum >= 100 if minimum > 0 else False

    def transform(value):
        return math.log10(value) if use_log else value

    low = transform(minimum)
    high = transform(maximum)
    padding = (high - low) * 0.08 if high > low else max(abs(high) * 0.08, 0.1)
    low -= padding
    high += padding
    body = [
        '<text x="30" y="56" font-size="12" class="muted">'
        "Per-query median elapsed seconds; failed/no-median queries are omitted."
        "</text>"
    ]
    tick_count = 5
    for tick in range(tick_count + 1):
        position = tick / tick_count
        y = bottom - position * plot_height
        value = low + position * (high - low)
        display_value = 10**value if use_log else value
        body.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" '
            f'y2="{y:.2f}" class="grid"/>'
            f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" '
            f'font-size="10" class="muted">{display_value:.3g}</text>'
        )
    body.append(
        f'<text x="22" y="{(top+bottom)/2:.2f}" text-anchor="middle" '
        'font-size="11" class="muted" '
        f'transform="rotate(-90 22 {(top+bottom)/2:.2f})">'
        f"Median seconds{' (log scale)' if use_log else ''}</text>"
    )
    point_sets = []
    for index, key in enumerate(("run1_median_seconds", "run2_median_seconds")):
        points = []
        for query_index, row in enumerate(scale_rows):
            value = row[key]
            if value is None:
                continue
            x = (
                left
                if len(scale_rows) == 1
                else left + query_index * plot_width / (len(scale_rows) - 1)
            )
            transformed = transform(value)
            y = bottom - (transformed - low) / (high - low) * plot_height
            points.append((x, y, query_index, value))
            body.append(
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.7" '
                f'fill="{COLORS[index]}"><title>{html.escape(row["query"])}; '
                f'{html.escape(labels[index])}: {value:.6f} seconds</title></circle>'
            )
        for first, second in zip(points, points[1:]):
            if second[2] == first[2] + 1:
                body.append(
                    f'<line x1="{first[0]:.2f}" y1="{first[1]:.2f}" '
                    f'x2="{second[0]:.2f}" y2="{second[1]:.2f}" '
                    f'stroke="{COLORS[index]}" stroke-width="1.5"/>'
                )
        point_sets.append(points)

    for query_index in range(0, len(queries), 10):
        x = (
            left
            if len(queries) == 1
            else left + query_index * plot_width / (len(queries) - 1)
        )
        body.append(
            f'<text x="{x:.2f}" y="{bottom+20}" text-anchor="middle" '
            f'font-size="9" class="muted">{html.escape(queries[query_index])}</text>'
        )
    body.append(
        f'<text x="{left}" y="{bottom+43}" font-size="11" '
        'class="muted">Query number</text>'
    )
    for index, label in enumerate(labels):
        x = left + index * 260
        body.append(
            f'<line x1="{x}" y1="590" x2="{x+26}" y2="590" '
            f'stroke="{COLORS[index]}" stroke-width="3"/>'
            f'<text x="{x+34}" y="594" font-size="11">'
            f"{html.escape(label)}</text>"
        )
    path.write_text(
        svg_document(
            f"SF{scale}: benchmark run comparison",
            "".join(body),
        ),
        encoding="utf-8",
        newline="\n",
    )


def write_workload_chart(path, rows, scales, labels):
    totals = []
    for scale in scales:
        scale_rows = [row for row in rows if row["scale_gb"] == scale]
        values = []
        for key in ("run1_median_seconds", "run2_median_seconds"):
            successful = [row[key] for row in scale_rows if row[key] is not None]
            values.append(sum(successful) if successful else None)
        totals.append((scale, values))

    width, height = 900, 520
    left, right, top, bottom = 95, 40, 80, 410
    plot_width = width - left - right
    plot_height = bottom - top
    max_value = max(
        (value for _, pair in totals for value in pair if value is not None),
        default=1.0,
    )
    max_value = max_value * 1.15 if max_value else 1.0
    body = [
        '<text x="30" y="56" font-size="12" class="muted">'
        "Sum of successful per-query median runtimes; not a single serial "
        "workload execution time."
        "</text>"
    ]
    for tick in range(6):
        value = max_value * tick / 5
        y = bottom - plot_height * tick / 5
        body.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" '
            f'y2="{y:.2f}" class="grid"/>'
            f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" '
            f'font-size="10" class="muted">{value:.3g}</text>'
        )
    group_width = plot_width / max(1, len(totals))
    bar_width = min(54, group_width * 0.28)
    for index, (scale, values) in enumerate(totals):
        center = left + group_width * (index + 0.5)
        for series, value in enumerate(values):
            if value is None:
                continue
            x = center + (series - 0.5) * (bar_width + 5) - bar_width / 2
            bar_height = value / max_value * plot_height
            body.append(
                f'<rect x="{x:.2f}" y="{bottom-bar_height:.2f}" '
                f'width="{bar_width:.2f}" height="{bar_height:.2f}" '
                f'fill="{COLORS[series]}"><title>SF{scale} '
                f'{html.escape(labels[series])}: {value:.3f} seconds</title></rect>'
            )
        body.append(
            f'<text x="{center:.2f}" y="{bottom+22}" text-anchor="middle" '
            f'font-size="11">SF{scale}</text>'
        )
    for index, label in enumerate(labels):
        x = left + index * 260
        body.append(
            f'<rect x="{x}" y="466" width="13" height="13" '
            f'fill="{COLORS[index]}"/>'
            f'<text x="{x+20}" y="478" font-size="11">'
            f"{html.escape(label)}</text>"
        )
    path.write_text(
        svg_document("Estimated workload median-time comparison", "".join(body)),
        encoding="utf-8",
        newline="\n",
    )
    return totals


def write_html(path, table_path, chart_files, totals, labels):
    table_rows = []
    for scale, values in totals:
        first, second = values
        if first is None or second is None:
            change = "N/A"
        elif first:
            change = f"{(second-first)/first*100:+.2f}%"
        else:
            change = "N/A"
        first_text = f"{first:.3f}" if first is not None else "N/A"
        second_text = f"{second:.3f}" if second is not None else "N/A"
        table_rows.append(
            "<tr>"
            f"<td>SF{scale}</td><td>{first_text}</td>"
            f"<td>{second_text}</td><td>{change}</td></tr>"
        )
    images = "".join(
        f'<section><h2>{html.escape(title)}</h2>'
        f'<img src="{html.escape(filename)}" alt="{html.escape(title)}">'
        "</section>"
        for title, filename in chart_files
    )
    relative_csv = html.escape(table_path.name)
    path.write_text(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Benchmark run comparison</title><style>"
        "body{font:16px Arial,sans-serif;max-width:1450px;margin:2rem auto;"
        "padding:0 1rem;color:#1f2937}img{max-width:100%;border:1px solid #ddd}"
        "table{border-collapse:collapse;margin:1rem 0}th,td{border:1px solid #ddd;"
        "padding:.5rem;text-align:right}th:first-child,td:first-child{text-align:left}"
        "section{margin:2rem 0}</style></head><body>"
        "<h1>Benchmark run comparison</h1>"
        f"<p>Run 1: <code>{html.escape(labels[0])}</code>; "
        f"Run 2: <code>{html.escape(labels[1])}</code>. "
        "Per-query charts use median elapsed time on the vertical axis. "
        "Each run contains five measured runs for all 99 queries at SF1/SF2/"
        "SF4/SF8 with no failures or timeouts. Timeout limits differed "
        "(1,800 seconds in Run 1 and 300 seconds in Run 2), but no queries "
        "timed out. See the CSV for the full query-by-query comparison.</p>"
        f'<p><a href="{relative_csv}">Download full comparison table (CSV)</a></p>'
        "<h2>Estimated workload totals</h2>"
        "<table><thead><tr><th>Scale</th>"
        f"<th>{html.escape(labels[0])} (s)</th>"
        f"<th>{html.escape(labels[1])} (s)</th>"
        "<th>Run 2 change</th></tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table>"
        + images
        + "</body></html>\n",
        encoding="utf-8",
        newline="\n",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compare two benchmark_runs folders with tables and charts."
    )
    parser.add_argument("run1", type=Path, help="First benchmark run directory")
    parser.add_argument("run2", type=Path, help="Second benchmark run directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: <run2>/plots/comparison_<run1-id>)",
    )
    args = parser.parse_args()
    run1 = args.run1.expanduser().resolve()
    run2 = args.run2.expanduser().resolve()
    for run in (run1, run2):
        if not run.is_dir():
            parser.error(f"benchmark run directory does not exist: {run}")
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else run2 / "plots" / f"comparison_{run1.name}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        first = load_run(run1)
        second = load_run(run2)
        rows = comparison_rows(first, second)
        scales = sorted(set(first).intersection(second))
        labels = (runtime_label(run1), runtime_label(run2))

        table_path = output_dir / "query_comparison.csv"
        write_comparison_csv(table_path, rows)

        chart_files = []
        workload_name = "estimated_workload_medians.svg"
        totals = write_workload_chart(
            output_dir / workload_name,
            rows,
            scales,
            labels,
        )
        chart_files.append(("Estimated workload medians by scale", workload_name))
        for scale in scales:
            filename = f"query_medians_sf{scale}.svg"
            write_scale_chart(output_dir / filename, scale, rows, labels)
            chart_files.append((f"Per-query medians at SF{scale}", filename))

        index_path = output_dir / "index.html"
        write_html(index_path, table_path, chart_files, totals, labels)
    except (OSError, ValueError, csv.Error) as error:
        raise SystemExit(f"ERROR: {error}") from error

    print(f"Compared {len(rows)} query-scale rows from {labels[0]} and {labels[1]}.")
    print(f"Comparison table: {table_path}")
    print(f"Comparison graphs and report: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
