#!/usr/bin/env python3
"""Plot baseline and experiment runtimes across SF1, SF2, SF4, and SF8."""

import argparse
import csv
import html
import math
from pathlib import Path


SCALES = (1, 2, 4, 8)
REQUIRED_FIELDS = {
    "query",
    "scale_gb",
    "results_equal",
    "baseline_mean_seconds",
    "baseline_stdev_seconds",
    "experiment_mean_seconds",
    "experiment_stdev_seconds",
    "baseline_only_rows",
    "experiment_only_rows",
}
SERIES = (
    ("baseline", "Baseline", "#2563eb"),
    ("experiment", "Experiment", "#dc2626"),
)


def parse_args():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Create one baseline-versus-experiment SVG chart per query, "
            "using per-scale benchmark means and standard deviations."
        )
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        default=root / "query_experiment_summary.csv",
        help="Summary CSV created by the experiment benchmark workflow.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=root,
        help="Experiments directory containing the Experiments_Q* folders.",
    )
    return parser.parse_args()


def load_summary(path):
    by_query = {}
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing_fields = REQUIRED_FIELDS.difference(reader.fieldnames or [])
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"{path} is missing required columns: {missing}")

        for row in reader:
            try:
                query = int(row["query"])
                scale = int(row["scale_gb"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"Invalid query or scale in {path}: {row}") from error
            if scale not in SCALES:
                raise ValueError(f"Unexpected scale SF{scale} in {path}")
            if scale in by_query.setdefault(query, {}):
                raise ValueError(f"Duplicate Q{query} SF{scale} row in {path}")

            point = {
                "scale": scale,
                "results_equal": row["results_equal"].strip().lower() == "true",
                "baseline_only_rows": row["baseline_only_rows"],
                "experiment_only_rows": row["experiment_only_rows"],
                "baseline": None,
                "experiment": None,
            }
            if point["results_equal"]:
                for variant in ("baseline", "experiment"):
                    try:
                        mean = float(row[f"{variant}_mean_seconds"])
                        stdev = float(row[f"{variant}_stdev_seconds"])
                    except (TypeError, ValueError) as error:
                        raise ValueError(
                            f"Missing or invalid {variant} timing for "
                            f"Q{query} SF{scale} in {path}"
                        ) from error
                    if not math.isfinite(mean) or mean < 0:
                        raise ValueError(
                            f"Invalid {variant} mean for Q{query} SF{scale}: {mean}"
                        )
                    if not math.isfinite(stdev) or stdev < 0:
                        raise ValueError(
                            f"Invalid {variant} standard deviation for "
                            f"Q{query} SF{scale}: {stdev}"
                        )
                    point[variant] = {"mean": mean, "stdev": stdev}
            by_query[query][scale] = point

    if not by_query:
        raise ValueError(f"No query results found in {path}")
    for query, points in by_query.items():
        missing = set(SCALES).difference(points)
        if missing:
            scales = ", ".join(f"SF{scale}" for scale in sorted(missing))
            raise ValueError(f"Q{query} is missing results for {scales}")
    return by_query


def svg_document(title, body):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="540" '
        'viewBox="0 0 900 540" role="img" '
        f'aria-label="{html.escape(title)}">'
        "<style>"
        "text{font-family:Arial,sans-serif;fill:#1f2937}"
        ".muted{fill:#6b7280}.grid{stroke:#e5e7eb;stroke-width:1}"
        ".axis{stroke:#6b7280;stroke-width:1}"
        "</style>"
        f'<text x="30" y="34" font-size="21" font-weight="bold">'
        f"{html.escape(title)}</text>{body}</svg>"
    )


def make_chart(query, points):
    width, height = 900, 540
    left, right, top, bottom = 95, 40, 85, 405
    plot_width = width - left - right
    plot_height = bottom - top
    valid_values = [
        point[variant]["mean"] + point[variant]["stdev"]
        for point in points.values()
        for variant, _, _ in SERIES
        if point["results_equal"] and point[variant] is not None
    ]
    maximum = max(valid_values, default=0.0)
    maximum = maximum * 1.15 if maximum else 1.0
    body = [
        '<text x="30" y="58" font-size="12" class="muted">'
        "Mean runtime +/- sample standard deviation; only result-matched "
        "baseline/experiment pairs are timed."
        "</text>"
        f'<text x="24" y="{(top + bottom) / 2:.2f}" text-anchor="middle" '
        'font-size="11" class="muted" '
        f'transform="rotate(-90 24 {(top + bottom) / 2:.2f})">'
        "Seconds</text>"
    ]

    tick_count = 5
    for tick in range(tick_count + 1):
        value = maximum * tick / tick_count
        y = bottom - plot_height * tick / tick_count
        body.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" '
            f'y2="{y:.2f}" class="grid"/>'
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" '
            f'font-size="10" class="muted">{value:.3g}</text>'
        )

    x_positions = {
        scale: left + index * plot_width / (len(SCALES) - 1)
        for index, scale in enumerate(SCALES)
    }
    for scale in SCALES:
        x = x_positions[scale]
        body.append(
            f'<line x1="{x:.2f}" y1="{top}" x2="{x:.2f}" '
            f'y2="{bottom}" class="grid"/>'
            f'<text x="{x:.2f}" y="{bottom + 24}" text-anchor="middle" '
            f'font-size="11">SF{scale}</text>'
        )

    for variant, label, color in SERIES:
        plotted = []
        for scale in SCALES:
            point = points[scale]
            timing = point[variant]
            if not point["results_equal"] or timing is None:
                continue
            x = x_positions[scale]
            mean = timing["mean"]
            stdev = timing["stdev"]
            y = bottom - mean / maximum * plot_height
            low_y = bottom - max(0.0, mean - stdev) / maximum * plot_height
            high_y = bottom - (mean + stdev) / maximum * plot_height
            plotted.append((x, y, SCALES.index(scale)))
            body.append(
                f'<line x1="{x:.2f}" y1="{high_y:.2f}" x2="{x:.2f}" '
                f'y2="{low_y:.2f}" stroke="{color}" stroke-width="1.5"/>'
                f'<line x1="{x - 5:.2f}" y1="{high_y:.2f}" '
                f'x2="{x + 5:.2f}" y2="{high_y:.2f}" '
                f'stroke="{color}" stroke-width="1.5"/>'
                f'<line x1="{x - 5:.2f}" y1="{low_y:.2f}" '
                f'x2="{x + 5:.2f}" y2="{low_y:.2f}" '
                f'stroke="{color}" stroke-width="1.5"/>'
                f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}">'
                f"<title>Q{query} SF{scale} {label}: "
                f"{mean:.6f} +/- {stdev:.6f} seconds</title></circle>"
            )
        for first, second in zip(plotted, plotted[1:]):
            if second[2] == first[2] + 1:
                body.append(
                    f'<line x1="{first[0]:.2f}" y1="{first[1]:.2f}" '
                    f'x2="{second[0]:.2f}" y2="{second[1]:.2f}" '
                    f'stroke="{color}" stroke-width="2.5"/>'
                )

    has_mismatches = any(
        not points[scale]["results_equal"] for scale in SCALES
    )
    if has_mismatches:
        failed_scales = ", ".join(
            f"SF{scale}" for scale in SCALES if not points[scale]["results_equal"]
        )
        note = f"Not timed due to result mismatches: {failed_scales}"
        body.append(
            f'<text x="{left}" y="{bottom + 58}" font-size="11" '
            f'fill="#b91c1c">{html.escape(note)}</text>'
        )

    legend_y = 500 if has_mismatches else 470
    for index, (variant, label, color) in enumerate(SERIES):
        x = left + index * 160
        body.append(
            f'<line x1="{x}" y1="{legend_y}" x2="{x + 24}" '
            f'y2="{legend_y}" stroke="{color}" stroke-width="3"/>'
            f'<circle cx="{x + 12}" cy="{legend_y}" r="4" fill="{color}"/>'
            f'<text x="{x + 32}" y="{legend_y + 4}" font-size="12">'
            f"{html.escape(label)}</text>"
        )
    body.append(
        f'<text x="{width - right}" y="518" text-anchor="end" '
        'font-size="10" class="muted">Scale factor</text>'
    )
    return svg_document(f"Q{query}: baseline vs experiment runtime", "".join(body))


def write_index(output_root, chart_paths):
    entries = []
    for query, path in chart_paths:
        relative = path.relative_to(output_root).as_posix()
        entries.append(
            f'<li><a href="{html.escape(relative)}">Q{query}</a></li>'
        )
    index = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Query experiment comparison graphs</title>"
        "<style>body{font-family:Arial,sans-serif;margin:2rem;color:#1f2937}"
        "li{margin:.5rem}</style></head><body>"
        "<h1>Query experiment comparison graphs</h1>"
        "<p>Each graph compares the baseline and experiment mean runtimes "
        "across SF1, SF2, SF4, and SF8. Error bars show sample standard "
        "deviation. Result-mismatched pairs are not timed.</p><ul>"
        + "".join(entries)
        + "</ul></body></html>"
    )
    path = output_root / "results_comparison" / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(index, encoding="utf-8", newline="\n")
    return path


def main():
    args = parse_args()
    summary_path = args.summary_csv.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    if not summary_path.is_file():
        raise SystemExit(f"Summary CSV does not exist: {summary_path}")

    try:
        by_query = load_summary(summary_path)
    except (OSError, ValueError) as error:
        raise SystemExit(f"Could not load benchmark summary: {error}") from error

    chart_paths = []
    for query, points in sorted(by_query.items()):
        query_root = output_root / f"Experiments_Q{query}"
        if not query_root.is_dir():
            raise SystemExit(f"Experiment folder does not exist: {query_root}")
        output_dir = query_root / "results_comparison"
        output_dir.mkdir(parents=True, exist_ok=True)
        chart_path = output_dir / f"query{query}_scale_comparison.svg"
        chart_path.write_text(
            make_chart(query, points),
            encoding="utf-8",
            newline="\n",
        )
        chart_paths.append((query, chart_path))
        print(f"Created: {chart_path}")

    index_path = write_index(output_root, chart_paths)
    print(f"Created index: {index_path}")
    print(f"Created {len(chart_paths)} query comparison charts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
