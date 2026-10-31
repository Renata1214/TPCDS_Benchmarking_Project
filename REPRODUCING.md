# Reproducing the TPC-DS experiments

This guide walks through the project from a fresh checkout to generated data,
query execution, and benchmark results. It covers the TPC-DS work in this
repository; it is not an official TPC benchmark audit or a reproduction of the
TPC-DI project.

The recommended workflow uses Docker Compose so Linux tools and DuckDB are
consistent on Linux, WSL 2, and macOS. Generated files are written to the
repository through a bind mount and remain there after the container exits.

## What you will reproduce

1. Generate scale-specific DuckDB SQL from the TPC-DS query templates.
2. Generate TPC-DS data and load it into DuckDB databases.
3. Execute the full query workload at each selected scale and save measurements.
4. Optionally compare the baseline and optimized forms of Queries 4, 22, 47,
   and 74, including a result-equivalence check.

The default reference scale is 10 GB. The factors below therefore create 1, 2,
4, and 8 GB datasets:

| Factor | Scale | Data | Database |
|---:|---:|---|---|
| `0.1` | SF1 (1 GB) | `data/sf1/` | `duckdb/tpcds_sf1.duckdb` |
| `0.2` | SF2 (2 GB) | `data/sf2/` | `duckdb/tpcds_sf2.duckdb` |
| `0.4` | SF4 (4 GB) | `data/sf4/` | `duckdb/tpcds_sf4.duckdb` |
| `0.8` | SF8 (8 GB) | `data/sf8/` | `duckdb/tpcds_sf8.duckdb` |

These are physical data sizes, not the official TPC-DS scale-factor set.
Generating the larger scales can take considerable time and disk space.

## 1. Install prerequisites and get the project

Install Git and Docker with the Docker Compose v2 plugin. On Windows, use
Docker Desktop with WSL 2 integration and run these commands inside your WSL
distribution. On macOS, use Docker Desktop and a Bash-compatible terminal. On
Linux, Docker Engine and the Compose plugin are sufficient. Install Python 3
on the host as well if you plan to run the experiment comparisons or generate
the charts; those scripts use the Python standard library.

Clone the repository and enter its root directory:

```bash
git clone https://github.com/Renata1214/TPCDS_Benchmarking_Project.git
cd TPCDS_Benchmarking_Project
```

If reproducing a particular branch or revision, check it out before continuing:

```bash
git checkout <branch-or-commit>
```

Build the project image. It includes DuckDB CLI 1.4.3 by default and builds the
Linux TPC-DS generator tools:

```bash
docker --version
docker compose version
docker compose build tpcds
```

Use the same Docker environment and resource allocation for every run you
compare. The repository is mounted at `/workspace` in the container; data,
databases, generated SQL, and results persist in the checkout.

## 2. Generate the SQL workload

Generate the queries for SF1, SF2, SF4, and SF8:

```bash
docker compose run --rm tpcds \
  bash scripts/01_generate_queries.sh 1 2 4 8
```

The SQL is written to `queries/sf1/`, `queries/sf2/`, `queries/sf4/`, and
`queries/sf8/`. The SF1 workload is also copied to `queries/all_templates/`.
The generated files use the repository's query templates, including its
experimental rewrites. The generation report is
`results/generation_results.csv`.

Regenerating queries replaces the generated SQL in the selected scale
directories. For exact comparisons with an earlier run, keep and use the same
generated SQL and source revision.

## 3. Generate and load the data

Generate the four datasets and load them into DuckDB:

```bash
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e DSDGEN_VERBOSE=N \
  tpcds bash scripts/04_generate_scale_data.sh 0.1 0.2 0.4 0.8
```

The script creates the 25 TPC-DS `.dat` files for each scale, creates the
database schema, and loads the data. It reuses a complete dataset and database
if both already exist. Generation and load information is appended to
`results/data_generation.csv`.

To rebuild a scale after confirming no other process is writing to it, pass
`FORCE=1` for that run:

```bash
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e FORCE=1 \
  tpcds bash scripts/04_generate_scale_data.sh 0.4
```

This replaces the selected scale's generated data and database; it does not
resume an interrupted generation. Do not use `FORCE=1` unless you intend to
regenerate that scale.

## 4. Run the full query workload

Run all generated queries at the four scales, with one warm-up pass and five
measured executions per query:

```bash
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e WARMUP_RUNS=1 \
  -e REPEATS=5 \
  -e TIMEOUT_SECONDS=300 \
  tpcds bash scripts/05_run_scale_benchmarks.sh 0.1 0.2 0.4 0.8
```

Warm-ups are excluded from the measurements. Increase `REPEATS` for more
stable summaries, or adjust `TIMEOUT_SECONDS` for slower queries. The run
creates a new timestamped directory under `results/benchmark_runs/` containing:

- `query_metrics.csv`: one row per measured execution, with elapsed time,
  CPU/memory metrics, status, and log path.
- `summaries/query_summary_sfN.csv`: per-query timing and status summaries for
  each physical scale.
- `logs/`: individual DuckDB output and error logs.
- `metadata.txt`: run settings and environment details.

Check the summary CSVs and execution statuses before interpreting the timings.
Results depend on hardware, filesystem, DuckDB version, cache state, and
settings; they should not be presented as official TPC-DS results.

To generate charts and a sortable per-query CSV for a completed run, use its
timestamped directory:

```bash
python3 scripts/plot_benchmark_results.py \
  results/benchmark_runs/<run_id>
```

The generated report is in
`results/benchmark_runs/<run_id>/plots/index.html`; ranked details are in
`plots/ranked_queries.csv`.

### Run the main workflow in one command

After building the image, the same stages can be run together. This generates
queries if needed, generates/loads the requested data factors, and benchmarks
them:

```bash
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e WARMUP_RUNS=1 \
  -e REPEATS=5 \
  tpcds bash scripts/run_tpcds.sh 0.1 0.2 0.4 0.8
```

## 5. Compare the query experiments

The experiment runner compares result rows as multisets before timing, so
differences in row order do not count as mismatches, but duplicate counts are
preserved. If results differ, it stops without reporting a timing comparison.
The runner defaults to SF1, two warm-ups, ten measured runs, and Docker. Run
these commands from the repository root after SF1 has been generated and
loaded:

```bash
python3 Experiments/run_benchmark.py \
  --baseline Experiments/Experiments_Q4/query4_noChanges.sql \
  --experiment Experiments/Experiments_Q4/query4_experiment1.sql \
  --name q4

python3 Experiments/run_benchmark.py \
  --baseline Experiments/Experiments_Q22/query22_original.sql \
  --experiment Experiments/Experiments_Q22/query22_Experiment1.sql \
  --name q22

python3 Experiments/run_benchmark.py \
  --baseline Experiments/Experiments_Q47/query47_noChanges.sql \
  --experiment Experiments/Experiments_Q47/query47_Experiment1.sql \
  --name q47

python3 Experiments/run_benchmark.py \
  --baseline Experiments/Experiments_Q74/q74_nochanges.sql \
  --experiment Experiments/Experiments_Q74/q74_experiment1.sql \
  --name q74
```

Each command creates a new timestamped results directory in the corresponding
`Experiments/Experiments_QN/` folder. Inspect its `benchmark/` directory:

- `result_validation.csv` records whether the baseline and experiment returned
  equivalent results.
- `qN_summary.csv` reports the measured timing statistics.
- `qN_measurements.csv` contains the individual measured runs.
- `metadata.txt` and `run_metadata.txt` record the run configuration.

For a different scale or run count, add options such as
`--scale-gb 4 --warmups 2 --repeats 10`. Query 74's optimizer settings are
handled by the experiment runner.

## 6. Find the query-specific optimization reports

This guide explains how to reproduce the runs. The specific query rewrites,
their optimization rationale, and analysis should be described in the
corresponding query reports. Add the final report links or paths here:

| Query | Optimization report |
|---|---|
| Q4 | Add link/path to the Query 4 report |
| Q22 | Add link/path to the Query 22 report |
| Q47 | Add link/path to the Query 47 report |
| Q74 | Add link/path to the Query 74 report |
