# Reproducing the TPC-DS experiments

## One-command reproduction

From the repository root, run:

```bash
bash reproduce.sh
```

Docker Compose builds and starts the project container, generates the scale-specific queries, runs the benchmark, creates its plots, and compares it with the fixed baseline run `20261023_164300_814393`. The script prints the result and report locations when it finishes. With no argument, it reuses the existing DuckDB databases and does not generate data. 

To generate the data and databases as part of the run, use:

```bash
bash reproduce.sh --generate-data
```

Data is generated locally by the bundled TPC-DS tools.

The remainder of this document explains the steps performed in the background by this command, along with prerequisites, output details, and how to run individual steps.

The recommended workflow uses Docker Compose so Linux tools and DuckDB are consistent on Linux, WSL 2, and macOS.

The overall path is the following:

1. Generate scale-specific DuckDB SQL from the TPC-DS query templates that have the necessary optimizations.
2. Optionally generate TPC-DS data and load it into DuckDB databases.
3. Execute the full query workload at each selected scale and save measurements.
4. Compare the new benchmark run with baseline `20261023_164300_814393`.

The default reference scale is 10 GB. The factors below therefore create 1, 2, 4, and 8 GB datasets:

| Factor | Scale | Data | Database |
|---:|---:|---|---|
| `0.1` | SF1 (1 GB) | `data/sf1/` | `duckdb/tpcds_sf1.duckdb` |
| `0.2` | SF2 (2 GB) | `data/sf2/` | `duckdb/tpcds_sf2.duckdb` |
| `0.4` | SF4 (4 GB) | `data/sf4/` | `duckdb/tpcds_sf4.duckdb` |
| `0.8` | SF8 (8 GB) | `data/sf8/` | `duckdb/tpcds_sf8.duckdb` |

## 1. Install prerequisites

Install Git and Docker with the Docker Compose. On Windows, use Docker Desktop with WSL 2 integration and run these commands inside your WSL distribution. On macOS, use Docker Desktop and a Bash-compatible terminal. Install Python 3 on the host as well.

Clone the repository and enter its root directory:

```bash
git clone https://github.com/Renata1214/TPCDS_Benchmarking_Project.git
cd TPCDS_Benchmarking_Project
```

Build the project image. It includes DuckDB CLI by default and builds the Linux TPC-DS generator tools:

```bash
docker --version
docker compose version
docker compose build tpcds
```

The repository is mounted at `/workspace` in the container; data,
databases, generated SQL, and results persist in the checkout.

## 2. Generate the SQL workload

Generate the queries for SF1, SF2, SF4, and SF8:

```bash
docker compose run --rm tpcds \
  bash scripts/01_generate_queries.sh 1 2 4 8
```
The SQL is written to `queries/sf1/`, `queries/sf2/`, `queries/sf4/`, and `queries/sf8/`.
The generated files use the repository's query templates, including its
experimental rewrites. The generation report is
`results/generation_results.csv`.

Regenerating queries replaces the generated SQL in the selected scale
directories. For exact comparisons with an earlier run, keep and use the same generated SQL and source revision.

## 3. Generate and load the data

Generate the four datasets and load them into DuckDB:

```bash
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e DSDGEN_VERBOSE=N \
  tpcds bash scripts/04_generate_scale_data.sh 0.1 0.2 0.4 0.8
```

The script creates the 25 TPC-DS `.dat` files for each scale, creates the database schema, and loads the data. It reuses a complete dataset and database if both already exist. Generation and load information is appended to `results/data_generation.csv`.

## 4. Run the full query workload

Run all generated queries at the four scales, with one warm-up pass and five measured executions per query:

```bash
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e WARMUP_RUNS=1 \
  -e REPEATS=5 \
  -e TIMEOUT_SECONDS=300 \
  tpcds bash scripts/05_run_scale_benchmarks.sh 0.1 0.2 0.4 0.8
```

Warm-ups are excluded from the measurements. Increase `REPEATS` for more
stable summaries, or adjust `TIMEOUT_SECONDS` for slower queries. The run creates a new timestamped directory under `results/benchmark_runs/` containing:

- `query_metrics.csv`: one row per measured execution, with elapsed time, CPU/memory metrics, status, and log path.
- `summaries/query_summary_sfN.csv`: per-query timing and status summaries for each physical scale.
- `logs/`: individual DuckDB output and error logs.
- `metadata.txt`: run settings and environment details.


The obtained results depend on hardware, filesystem, DuckDB version, cache state, and settings.
To generate charts and a sortable per-query CSV for a completed run, use its timestamped directory:

```bash
python3 scripts/plot_benchmark_results.py \
  results/benchmark_runs/<run_id>
```

The generated report is in
`results/benchmark_runs/<run_id>/plots/index.html`; ranked details are in`plots/ranked_queries.csv`.

To compare two completed benchmark runs, generate a per-query CSV table, SVG graphs by scale, a workload-median graph, and an HTML report:

```bash
python3 scripts/compare_benchmark_runs.py \
  results/benchmark_runs/<first_run_id> \
  results/benchmark_runs/<second_run_id>
```

By default, comparison files are written under
`<second_run>/plots/comparison_<first_run_id>/`.
