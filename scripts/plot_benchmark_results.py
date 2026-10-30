#!/usr/bin/env python3
"""Create SVG visualizations from one benchmark run's per-scale summaries."""

import argparse
import csv
import html
import math
import re
from pathlib import Path


SUMMARY_FILENAME = re.compile(r"query_summary_sf(\d+)\.csv", re.IGNORECASE)
QUERY_NUMBER = re.compile(r"query(\d+)", re.IGNORECASE)
SUMMARY_FIELDS = {
    "factor",
    "scale_gb",
    "query",
    "runs",
    "working",
    "failed",
    "timeouts",
    "median_elapsed_seconds",
}
COLORS = ("#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#0891b2")


def numeric_query_key(query):
    match = QUERY_NUMBER.fullmatch(query)
    if not match:
        raise ValueError(f"unexpected query name in summary: {query!r}")
    return int(match.group(1))


def load_summaries(run_dir):
    summaries = []
    for path in run_dir.iterdir():
        match = SUMMARY_FILENAME.fullmatch(path.name)
        if path.is_file() and match:
            summaries.append((int(match.group(1)), path))
    summaries.sort(key=lambda item: item[0])
    if not summaries:
        raise ValueError(f"no query_summary_sf<scale>.csv files found in {run_dir}")

    by_scale = []
    seen_factors = set()
    for scale_gb, path in summaries:
        with path.open(newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            missing_fields = SUMMARY_FIELDS.difference(reader.fieldnames or [])
            if missing_fields:
                fields = ", ".join(sorted(missing_fields))
                raise ValueError(f"{path} is missing required columns: {fields}")

            rows = []
            factor_values = set()
            for row in reader:
                try:
                    factor = float(row["factor"])
                    row_scale = int(row["scale_gb"])
                    runs = int(row["runs"])
                    working = int(row["working"])
                    failed = int(row["failed"])
                    timeouts = int(row["timeouts"])
                    query_number = numeric_query_key(row["query"])
                    median = (
                        float(row["median_elapsed_seconds"])
                        if row["median_elapsed_seconds"]
                        else None
                    )
                except (TypeError, ValueError) as error:
                    raise ValueError(f"invalid summary row in {path}: {row}") from error
                if not math.isfinite(factor) or factor <= 0:
                    raise ValueError(f"invalid factor in {path}: {row['factor']!r}")
                if median is not None and (
                    not math.isfinite(median) or median < 0
                ):
                    raise ValueError(
                        f"invalid median time in {path}: "
                        f"{row['median_elapsed_seconds']!r}"
                    )
                if row_scale != scale_gb:
                    raise ValueError(
                        f"scale mismatch in {path}: row says SF{row_scale}"
                    )
                factor_values.add(factor)
                rows.append(
                    {
                        "factor": factor,
                        "scale_gb": row_scale,
                        "query": row["query"],
                        "query_number": query_number,
                        "runs": runs,
                        "working": working,
                        "failed": failed,
                        "timeouts": timeouts,
                        "median": median,
                    }
                )
        if len(factor_values) != 1:
            raise ValueError(f"expected exactly one factor in {path}, found {factor_values}")
        factor = next(iter(factor_values))
        if factor in seen_factors:
            raise ValueError(f"duplicate factor {factor:g} across scale summaries")
        seen_factors.add(factor)
        by_scale.append(
            {
                "factor": factor,
                "scale_gb": scale_gb,
                "rows": sorted(rows, key=lambda row: row["query_number"]),
            }
        )

    by_scale.sort(key=lambda summary: summary["factor"])
    query_names = sorted(
        {row["query"] for summary in by_scale for row in summary["rows"]},
        key=numeric_query_key,
    )
    return by_scale, query_names


def svg_document(width, height, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{html.escape(title)}">'
        '<style>text{font-family:Arial,sans-serif;fill:#1f2937}'
        '.muted{fill:#6b7280}.grid{stroke:#e5e7eb;stroke-width:1}'
        '.axis{stroke:#6b7280;stroke-width:1}.line{fill:none;stroke-width:2}'
        '</style>'
        f'<text x="24" y="28" font-size="20" font-weight="bold">'
        f'{html.escape(title)}</text>{body}</svg>'
    )


def write_svg(path, width, height, body, title):
    path.write_text(
        svg_document(width, height, body, title),
        encoding="utf-8",
        newline="\n",
    )


def query_grid_chart(output_path, summaries, query_names):
    columns = 10
    rows = max(1, math.ceil(len(query_names) / columns))
    cell_width = 174
    cell_height = 124
    left = 44
    top = 54
    width = left + columns * cell_width + 12
    height = top + rows * cell_height + 32
    body = [
        '<text x="24" y="47" font-size="11" class="muted">'
        "Seconds per query; each panel uses its own y-axis scale."
        "</text>"
    ]
    values_by_query = {
        query: [
            next(
                (row["median"] for row in summary["rows"] if row["query"] == query),
                None,
            )
            for summary in summaries
        ]
        for query in query_names
    }

    for index, query in enumerate(query_names):
        grid_x = index % columns
        grid_y = index // columns
        x0 = left + grid_x * cell_width
        y0 = top + grid_y * cell_height
        plot_left = x0 + 25
        plot_right = x0 + cell_width - 10
        plot_top = y0 + 18
        plot_bottom = y0 + cell_height - 27
        values = values_by_query[query]
        valid = [value for value in values if value is not None]
        maximum = max(valid, default=0.0) * 1.12
        if maximum <= 0:
            maximum = 1.0
        body.append(
            f'<text x="{x0 + 5}" y="{y0 + 12}" font-size="11" '
            f'font-weight="bold">{html.escape(query)}</text>'
        )
        body.append(
            f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" '
            f'y2="{plot_bottom}" class="axis"/>'
        )
        body.append(
            f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" '
            f'y2="{plot_bottom}" class="axis"/>'
        )
        body.append(
            f'<text x="{plot_left - 3}" y="{plot_top + 4}" text-anchor="end" '
            f'font-size="8" class="muted">{maximum:.2g}</text>'
        )
        points = []
        for factor_index, value in enumerate(values):
            x = (
                plot_left
                if len(summaries) == 1
                else plot_left
                + factor_index * (plot_right - plot_left) / (len(summaries) - 1)
            )
            y = (
                plot_bottom
                if value is None
                else plot_bottom - value / maximum * (plot_bottom - plot_top)
            )
            if value is not None:
                points.append((x, y, factor_index))
                body.append(
                    f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.6" '
                    f'fill="{COLORS[factor_index % len(COLORS)]}">'
                    f'<title>{html.escape(query)}; factor '
                    f'{summaries[factor_index]["factor"]:g}: {value:.3f} s'
                    "</title></circle>"
                )
        for first, second in zip(points, points[1:]):
            if second[2] == first[2] + 1:
                body.append(
                    f'<line x1="{first[0]:.2f}" y1="{first[1]:.2f}" '
                    f'x2="{second[0]:.2f}" y2="{second[1]:.2f}" '
                    f'stroke="{COLORS[second[2] % len(COLORS)]}" '
                    'stroke-width="1.5"/>'
                )
        for factor_index, summary in enumerate(summaries):
            x = (
                plot_left
                if len(summaries) == 1
                else plot_left
                + factor_index * (plot_right - plot_left) / (len(summaries) - 1)
            )
            body.append(
                f'<text x="{x:.2f}" y="{plot_bottom + 12}" text-anchor="middle" '
                f'font-size="8" class="muted">{summary["factor"]:g}</text>'
            )
    legend_y = height - 7
    legend_x = left
    for index, summary in enumerate(summaries):
        x = legend_x + index * 104
        body.append(
            f'<circle cx="{x}" cy="{legend_y - 4}" r="4" '
            f'fill="{COLORS[index % len(COLORS)]}"/>'
            f'<text x="{x + 8}" y="{legend_y}" font-size="10">'
            f'factor {summary["factor"]:g} (SF{summary["scale_gb"]})</text>'
        )
    write_svg(
        output_path,
        width,
        height,
        "".join(body),
        "Per-query median runtime across scale factors",
    )


def ranked_chart(output_path, summary):
    rows = sorted(
        summary["rows"],
        key=lambda row: (
            row["median"] is None,
            row["median"] if row["median"] is not None else float("inf"),
            row["query_number"],
        ),
    )
    width = 1100
    row_height = 20
    top = 54
    left = 100
    right = 100
    height = top + len(rows) * row_height + 42
    max_value = max(
        (row["median"] for row in rows if row["median"] is not None),
        default=0.0,
    )
    max_value = max_value or 1.0
    plot_width = width - left - right
    body = [
        '<text x="24" y="48" font-size="11" class="muted">'
        "Fastest to slowest by median successful measured execution; "
        "queries without a successful median appear last."
        "</text>"
    ]
    tick_count = 5
    for tick in range(tick_count + 1):
        value = max_value * tick / tick_count
        x = left + plot_width * tick / tick_count
        body.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
            f'y2="{height - 32}" class="grid"/>'
            f'<text x="{x:.2f}" y="{top - 8}" text-anchor="middle" '
            f'font-size="9" class="muted">{value:.3g} s</text>'
        )
    for index, row in enumerate(rows):
        y = top + index * row_height
        label = html.escape(row["query"])
        body.append(
            f'<text x="{left - 10}" y="{y + 13}" text-anchor="end" '
            f'font-size="10">{label}</text>'
        )
        if row["median"] is None:
            status = (
                f'no median; {row["working"]}/{row["runs"]} working, '
                f'{row["failed"]} failed, {row["timeouts"]} timed out'
            )
            body.append(
                f'<text x="{left}" y="{y + 13}" font-size="9" '
                f'fill="#6b7280">No successful median</text>'
                f'<title>{html.escape(status)}</title>'
            )
        else:
            bar_width = row["median"] / max_value * plot_width
            status = (
                f'{row["median"]:.3f} s median; {row["working"]}/{row["runs"]} '
                f'working; {row["failed"]} failed; {row["timeouts"]} timed out'
            )
            body.append(
                f'<rect x="{left}" y="{y + 2}" width="{bar_width:.2f}" '
                f'height="15" fill="#2563eb">'
                f'<title>{html.escape(status)}</title></rect>'
                f'<text x="{left + bar_width + 5:.2f}" y="{y + 13}" '
                f'font-size="9" class="muted">{row["median"]:.3f}</text>'
            )
    write_svg(
        output_path,
        width,
        height,
        "".join(body),
        f"Query runtimes ranked fastest to slowest — factor "
        f'{summary["factor"]:g} (SF{summary["scale_gb"]})',
    )
    return rows


def scale_overview_chart(output_path, summaries):
    width = 850
    height = 430
    left, right, top, bottom = 95, 35, 74, 325
    plot_width = width - left - right
    plot_height = bottom - top
    totals = []
    for summary in summaries:
        successful = [
            row["median"] for row in summary["rows"] if row["median"] is not None
        ]
        totals.append((sum(successful), len(successful), len(summary["rows"])))
    maximum = max((total[0] for total in totals), default=0.0) or 1.0
    body = [
        '<text x="24" y="48" font-size="11" class="muted">'
        "Sum of per-query median times; includes only queries with a successful "
        "median. Check completion chart alongside this estimate."
        "</text>"
    ]
    for tick in range(6):
        value = maximum * tick / 5
        y = bottom - plot_height * tick / 5
        body.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" '
            f'y2="{y:.2f}" class="grid"/>'
            f'<text x="{left - 8}" y="{y + 4:.2f}" text-anchor="end" '
            f'font-size="9" class="muted">{value:.3g} s</text>'
        )
    step = plot_width / max(1, len(summaries))
    bar_width = min(85, step * 0.55)
    for index, (summary, (total, included, count)) in enumerate(
        zip(summaries, totals)
    ):
        x = left + step * (index + 0.5) - bar_width / 2
        bar_height = total / maximum * plot_height
        body.append(
            f'<rect x="{x:.2f}" y="{bottom - bar_height:.2f}" '
            f'width="{bar_width:.2f}" height="{bar_height:.2f}" '
            f'fill="{COLORS[index % len(COLORS)]}">'
            f'<title>{total:.3f} seconds; medians available for '
            f'{included}/{count} queries</title></rect>'
            f'<text x="{x + bar_width / 2:.2f}" y="{bottom + 20}" '
            f'text-anchor="middle" font-size="10">'
            f'{summary["factor"]:g} (SF{summary["scale_gb"]})</text>'
            f'<text x="{x + bar_width / 2:.2f}" '
            f'y="{bottom - bar_height - 7:.2f}" text-anchor="middle" '
            f'font-size="9" class="muted">{total:.3g}</text>'
        )
    write_svg(
        output_path,
        width,
        height,
        "".join(body),
        "Estimated workload runtime by scale",
    )


def completion_chart(output_path, summaries):
    width = 850
    height = 430
    left, right, top, bottom = 130, 40, 78, 330
    plot_width = width - left - right
    statuses = ("working", "failed", "timeouts")
    status_colors = {"working": "#16a34a", "failed": "#dc2626", "timeouts": "#f59e0b"}
    body = [
        '<text x="24" y="49" font-size="11" class="muted">'
        "Counts across all measured query executions."
        "</text>"
    ]
    max_count = max(
        (
            sum(row[status] for row in summary["rows"])
            for summary in summaries
            for status in statuses
        ),
        default=0,
    )
    max_count = max_count or 1
    for tick in range(6):
        count = max_count * tick / 5
        x = left + plot_width * tick / 5
        body.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
            f'y2="{bottom}" class="grid"/>'
            f'<text x="{x:.2f}" y="{bottom + 16}" text-anchor="middle" '
            f'font-size="9" class="muted">{count:.0f}</text>'
        )
    row_height = min(45, (bottom - top) / max(1, len(summaries)))
    for index, summary in enumerate(summaries):
        y = top + index * row_height + row_height * 0.25
        body.append(
            f'<text x="{left - 10}" y="{y + 12}" text-anchor="end" '
            f'font-size="10">{summary["factor"]:g} '
            f'(SF{summary["scale_gb"]})</text>'
        )
        x = left
        for status in statuses:
            count = sum(row[status] for row in summary["rows"])
            bar_width = count / max_count * plot_width
            if bar_width:
                body.append(
                    f'<rect x="{x:.2f}" y="{y}" width="{bar_width:.2f}" '
                    f'height="17" fill="{status_colors[status]}">'
                    f'<title>{status}: {count}</title></rect>'
                )
                if bar_width >= 25:
                    body.append(
                        f'<text x="{x + bar_width / 2:.2f}" y="{y + 12}" '
                        f'text-anchor="middle" font-size="9" fill="white">'
                        f'{count}</text>'
                    )
                x += bar_width
    legend_y = height - 38
    for index, status in enumerate(statuses):
        x = left + index * 110
        body.append(
            f'<rect x="{x}" y="{legend_y - 10}" width="12" height="12" '
            f'fill="{status_colors[status]}"/>'
            f'<text x="{x + 18}" y="{legend_y}" font-size="10">{status}</text>'
        )
    write_svg(
        output_path,
        width,
        height,
        "".join(body),
        "Measured execution outcomes by scale",
    )


def write_rankings(path, summaries):
    fields = [
        "factor",
        "scale_gb",
        "rank_fastest_to_slowest",
        "query",
        "median_elapsed_seconds",
        "runs",
        "working",
        "failed",
        "timeouts",
    ]
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for summary in summaries:
            rows = sorted(
                summary["rows"],
                key=lambda row: (
                    row["median"] is None,
                    row["median"] if row["median"] is not None else float("inf"),
                    row["query_number"],
                ),
            )
            for rank, row in enumerate(rows, start=1):
                writer.writerow(
                    {
                        "factor": summary["factor"],
                        "scale_gb": summary["scale_gb"],
                        "rank_fastest_to_slowest": rank,
                        "query": row["query"],
                        "median_elapsed_seconds": (
                            f'{row["median"]:.3f}'
                            if row["median"] is not None
                            else ""
                        ),
                        "runs": row["runs"],
                        "working": row["working"],
                        "failed": row["failed"],
                        "timeouts": row["timeouts"],
                    }
                )


def write_report(path, chart_files, factor_labels):
    links = "\n".join(
        f'<section><h2>{html.escape(title)}</h2>'
        f'<img src="{html.escape(filename)}" alt="{html.escape(title)}">'
        "</section>"
        for title, filename in chart_files
    )
    factors = ", ".join(html.escape(label) for label in factor_labels)
    path.write_text(
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>TPC-DS benchmark charts</title>"
        "<style>body{font:16px Arial,sans-serif;max-width:1500px;margin:2rem auto;"
        "padding:0 1rem;color:#1f2937}section{margin:2rem 0}"
        "img{max-width:100%;height:auto;border:1px solid #ddd}"
        "p{line-height:1.5}</style><body>"
        "<h1>TPC-DS benchmark charts</h1>"
        "<p>Factors: " + factors + ". Per-query charts show medians from "
        "successful measured executions. Each panel in the query grid has its "
        "own y-axis, so compare trends within a query; use ranked charts for "
        "absolute time comparisons. The workload total is the sum of query "
        "medians and excludes queries with no successful median. Review "
        "execution outcomes before interpreting that total.</p>"
        + links
        + "<p>Exact per-query rankings are in <code>ranked_queries.csv</code>.</p>"
        "</body></html>\n",
        encoding="utf-8",
        newline="\n",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate charts from benchmark_runs/<run_id>/summaries."
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="A benchmark run folder containing summaries/query_summary_sf*.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output folder (default: <run_dir>/plots).",
    )
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        parser.error(f"benchmark run directory does not exist: {run_dir}")
    summary_dir = run_dir / "summaries"
    if not summary_dir.is_dir():
        parser.error(f"summary directory does not exist: {summary_dir}")
    output_dir = args.output_dir.resolve() if args.output_dir else run_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        summaries, query_names = load_summaries(summary_dir)
        if not query_names:
            raise ValueError(f"no query rows found in {summary_dir}")
        chart_files = []
        grid_name = "query_runtime_grid.svg"
        query_grid_chart(output_dir / grid_name, summaries, query_names)
        chart_files.append(("Per-query runtime grid", grid_name))

        for summary in summaries:
            filename = f'ranked_queries_sf{summary["scale_gb"]}.svg'
            ranked_chart(output_dir / filename, summary)
            chart_files.append(
                (
                    f'Fastest to slowest — factor {summary["factor"]:g} '
                    f'(SF{summary["scale_gb"]})',
                    filename,
                )
            )

        totals_name = "estimated_workload_time.svg"
        scale_overview_chart(output_dir / totals_name, summaries)
        chart_files.append(("Estimated workload runtime by scale", totals_name))
        outcomes_name = "execution_outcomes.svg"
        completion_chart(output_dir / outcomes_name, summaries)
        chart_files.append(("Execution outcomes by scale", outcomes_name))
        rankings_name = "ranked_queries.csv"
        write_rankings(output_dir / rankings_name, summaries)
        report_name = "index.html"
        write_report(
            output_dir / report_name,
            chart_files,
            [
                f'{summary["factor"]:g} (SF{summary["scale_gb"]})'
                for summary in summaries
            ],
        )
    except (OSError, ValueError, csv.Error) as error:
        raise SystemExit(f"ERROR: {error}") from error

    print(f"Created {len(chart_files)} SVG charts and rankings in {output_dir}")
    print(f"Open {output_dir / report_name} to view the charts.")


if __name__ == "__main__":
    main()
