# Reproducing My TPC-DS DuckDB Results

This guide documents my own workflow and does not replace the repository's
existing `REPRODUCING.md`.

## 1. Environment

Recorded for the completed benchmark run:

- DuckDB CLI 1.4.3 (Andium)
- Linux container
- 18 reported CPUs
- Benchmark timeout: 300 seconds per execution
- Reference scale: 10 GB

The repository is run through Docker Compose using the `tpcds` service
defined in `compose.yaml`. The project is mounted at `/workspace` in the
container.

## 2. Required files

For a given scale factor, the benchmark runner expects:

- Database: `duckdb/tpcds_sfN.duckdb`
- Query directory: `queries/sfN/`
- Query files named `query<number>.sql`

For example, SF5 uses `duckdb/tpcds_sf5.duckdb` and `queries/sf5/`.
The scale factor passed to the runner is multiplied by
`REFERENCE_SCALE_GB`, which defaults to 10 GB.

## 3. Run a benchmark

From the repository root on the Mac, first check that the expected database
and query files exist:

```bash
for sf in 1 2 4 5 8 10; do
  test -f "duckdb/tpcds_sf${sf}.duckdb" || echo "Missing SF${sf} database"
  count=$(find "queries/sf${sf}" -maxdepth 1 -type f -name 'query*.sql' | wc -l)
  echo "SF${sf}: ${count} query files"
done
```

To benchmark SF10 only (SF5 is already complete) with three measured repetitions, one warm-up, and
a 300-second per-execution timeout:

```bash
docker compose run --rm --no-deps --entrypoint bash tpcds -lc '
  set -e
  export DUCKDB_BIN=/usr/local/bin/duckdb
  export REPEATS=3
  export WARMUP_RUNS=1
  export TIMEOUT_SECONDS=300
  export REFERENCE_SCALE_GB=10
  bash scripts/05_run_scale_benchmarks.sh 1.0
'
```

This command runs SF10 only. SF5 was benchmarked separately. SF10 queries may be
memory-intensive; inspect the resulting logs and summaries rather than
assuming every query completed. Do not overwrite or delete earlier results.

The runner creates a new timestamped directory under
`results/benchmark_runs/` for each invocation. It writes `metadata.txt`,
`query_metrics.csv`, per-query logs under `logs/`, and per-scale summaries
under `summaries/`.

## 4. Existing completed run

The main completed run documented in my report is:

`results/benchmark_runs/20261028_110053_343884/`

Its key artifacts are:

- `metadata.txt`
- `query_metrics.csv`
- `summaries/cross_scale_comparison.csv`
- `summaries/query_summary_sf1.csv`
- `summaries/query_summary_sf2.csv`
- `summaries/query_summary_sf4.csv`
- `summaries/query_summary_sf8.csv`
- `logs/`

The main run contains SF1, SF2, SF4, and SF8 measurements. SF5 was measured separately.

### Separate SF5 run

The SF5 run is stored in `results/benchmark_runs/20261028_115520_962190/`.

The saved raw metrics contain 297 successful measured executions: 99
queries with three repetitions each, with no measured failures or timeouts.
The median of the per-query medians was 0.037 seconds; the minimum query
median was 0.005 seconds and the maximum was 3.831 seconds.

The DuckDB process stalled during shutdown after the last query. The raw
metrics were preserved, and `summaries/query_summary_sf5.csv` was
reconstructed from those saved metrics. Timings were not rerun; the
summary reconstruction does not mean the runner shut down normally.

## 5. Inspect a run

After a benchmark completes, inspect the output directory:

```bash
find results/benchmark_runs -mindepth 1 -maxdepth 1 -type d -print | sort
```

Then set `RUN_DIR` to the new directory and inspect its metadata and
summaries:

```bash
RUN_DIR="results/benchmark_runs/REPLACE_WITH_RUN_ID"

cat "$RUN_DIR/metadata.txt"
column -s, -t < "$RUN_DIR/query_metrics.csv" | head -30
find "$RUN_DIR/summaries" -maxdepth 1 -type f -print | sort
```

Replace `REPLACE_WITH_RUN_ID` with the actual timestamped directory name.
Check failed warm-ups as well as measured runs. A query can appear in a
summary even when it has fewer measured repetitions than expected.

## 6. Optimization artifacts

The original and optimized SQL snapshots are stored in:

- `queries/optimization/original/`
- `queries/optimization/optimized/`

Supporting analysis is stored in:

- `reports/optimization/README.md`
- `reports/optimization/statement_timing_summary.csv`
- `reports/optimization/wall_clock_summary.csv`

The statement-timing and wall-clock results use different measurement
methods. Keep them labelled separately in any reproduced report.

## 7. Reproducibility notes

- Keep the DuckDB version, scale, repetitions, warm-ups, timeout, and runtime
  settings with each result set.
- Do not count warm-ups as measured executions.
- Report failed warm-ups and missing measurements explicitly.
- Do not compare the separate single-thread Q22 test directly with the main
  benchmark because its settings differ.
- Database file sizes are storage sizes, not the logical TPC-DS scale.
- Benchmark outputs under `results/` may be ignored by Git. Preserve the
  required raw metrics, metadata, logs, and summaries separately if they
  must be submitted or shared.
- This guide describes the current workflow; verify the actual generated
  artifacts before reporting a new run as complete.
