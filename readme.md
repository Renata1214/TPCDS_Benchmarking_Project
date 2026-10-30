# Project Description 

Note. This repository only covers the first part of the project described below. 

For the detailed Docker impact, current artifact status, recovery notes, and step-by-step reproduction procedure, see [REPRODUCING.md](./REPRODUCING.md).

TPC is a non-profit corporation that defines transaction processing and database benchmarks and disseminates objective, verifiable TPC performance data to the industry. Regarding data warehouses, two TPC benchmarks are relevant:

TPC-DS, the Decision Support Benchmark, which models the decision support functions of a retail product supplier.
TPC-DI, the Data Integration Support Benchmark, which models a typical ETL process that loads a data warehouse.
The project of the course consist of 2 parts:

Part I: Implement the TPC-DS benchmark (deadline 1/11/2026)
Part II: Implement the TPC-DI benchmark (deadline 24/12/2026)
You have free choice to use the tools on which the two benchmarks will be implemented. For example, the TPC-DS benchmark could be implemented on SQL Server Analysis Services, Pentaho Analysis Services (aka Mondrian), etc. Similarly, the TPC-DI benchmark could be implemented on SQL Server Integration Services, Pentaho Data Integration, Talend Data Studio, SQL scripts, etc., which then load the data warehouse on a DBMS such as SQL Server, Oracle, PostgreSQL, etc.

Furthermore, both benchmarks must be implemented with several scale factors, which determine the size of the resulting data warehouse. You DO NOT need to use the scale factors mentioned in the TPC requirements. The pedagogical objectives aimed at is that you learn how to properly perform a benchmark. Therefore, you need to estimate the biggest scale factor that you can put on your own computer: this will be your reference scale factor, say 1.0, and then you will need to have 3 smaller scale factors, e.g., at 0.1, 0.2, and 0.5 of the full size in order to see the evolution of the performance.

The project is carried out in groups of 3-4 persons, which will be the same for the two parts. Before you can submit part I of the project, you will have to register in a group. For this, please send an email to the lecturer with the information about your group by 1/10/2026 at the latest. The submission deadlines for parts I and II are strict.

The deliverables expected for each part of the project are the following:

A report in pdf explaining the essential aspects of your implementation, and
A zip file containing the code of your implementation, with all necessary instructions to be able to replicate your implementation by the lecturer in standard computing infrastructure.
The project evaluation will count for 30% of your total grade. This may seem undervalued, however, putting effort in the project will definitely help you in achieving a better understanding of the course material which will result in a better score in the paper exam which amounts for 70% of the grade.

## Running the TPC-DS scales with Docker

Docker provides the Linux TPC-DS generator tools, DuckDB CLI, and benchmark prerequisites without installing them in Windows or WSL. Install Docker Desktop with its WSL 2 backend, open a terminal at the repository root, then build and run the container:

```bash
docker compose build
docker compose run --rm tpcds
```

The default run uses reference scale 10 GB and factors `0.1`, `0.2`, and `0.5`. Pass factors to the workflow command to choose other scales:

```bash
docker compose run --rm tpcds bash scripts/run_tpcds.sh 0.1 0.2 0.5 1.0
```

Configuration can be supplied through environment variables. For example, to run each query three times:

```bash
docker compose run --rm -e REPEATS=3 -e REFERENCE_SCALE_GB=10 tpcds bash scripts/run_tpcds.sh 0.1 0.2 0.5
```

The repository is mounted at `/workspace`, so generated data, DuckDB databases, query files, and benchmark results remain in the project directories on the host after the container exits. The image compiles the Linux `dsdgen` and `dsqgen` tools and installs them into the mounted tools directory when it starts. Open an interactive shell instead of running the workflow with:

```bash
docker compose run --rm tpcds bash
```

For reliable benchmark timings, keep the Docker resource limits and host configuration consistent between runs. Docker Desktop may also perform better when the repository is stored in the WSL filesystem rather than on a Windows-mounted drive.

## Running the TPC-DS scales directly in WSL

The scripts below treat `REFERENCE_SCALE_GB` as the data size of relative factor `1.0`. The TPC-DS generator requires whole-number scale sizes of at least 1 GB. The default reference of `10` GB therefore makes factors `0.1`, `0.2`, and `0.5` generate 1, 2, and 5 GB datasets; factor `1.0` is 10 GB. Choose the largest reference your computer can handle, and choose factors/reference combinations whose products are whole-number GB values. An existing SF1 dataset/database is reused when the calculated physical scale is 1 GB.

### One-command workflow

From the WSL terminal, run this at the repository root:

```bash
bash scripts/run_tpcds.sh
```

This uses the default reference of 10 GB and factors `0.1`, `0.2`, and `0.5`. It creates the SQL workload only if it is missing, generates and loads the requested factors, and runs the benchmark. Pass other relative factors as arguments:

```bash
bash scripts/run_tpcds.sh 0.1 0.2 0.5 1.0
```

Set environment variables before the command to change configuration; for example, repeat each query three times:

```bash
REFERENCE_SCALE_GB=10 REPEATS=3 bash scripts/run_tpcds.sh 0.1 0.2 0.5
```

This command requires WSL prerequisites described below, including DuckDB CLI and the Linux TPC-DS generator tools. It uses existing generated query SQL when complete; set `REGENERATE_QUERIES=1` to explicitly recreate the SQL files.

The Query 4, 22, 47, and 74 templates in `Kit/DSGen-software-code-4.0.0/query_templates/` contain the project’s experimental rewrites. Query 4 pre-aggregates each sales channel by customer key and year, filters to the two target years, and joins the customer details after aggregation. Query 74 uses the cVariant join order; the query generator adds its `disabled_optimizers` setup and reset around generated Query 74 SQL. These modified templates produce a custom experimental workload, not the unmodified official TPC-DS query workload.

To refresh only the generated Query 22, 47, and 74 SQL files without deleting or regenerating the other queries, run:

```bash
bash scripts/01_update_experiment_queries.sh
```

By default, this updates SF1, SF2, SF4, SF8, and their SF1 `queries/all_templates/` copies. Pass scale sizes to update only selected scales, for example `bash scripts/01_update_experiment_queries.sh 1 4`.

### Prerequisites

- Run these commands from the WSL terminal.
- Build or otherwise provide the Linux `dsdgen` executable in `Kit/DSGen-software-code-4.0.0/tools/`. The Linux `dsqgen` executable is needed only if you need to regenerate the SQL workload.
- Install the DuckDB command-line executable as `duckdb`, plus GNU `time`, `timeout`, and Python 3. The scripts stop with an error if a required command is missing.
- Keep the repository in the WSL filesystem or access it via `/mnt/<drive>/...`. The scripts locate the repository relative to themselves.

If the Linux TPC-DS executables are missing, install the build tools (for example, `sudo apt install build-essential bison flex`) and build them from the tools directory:

```bash
cd Kit/DSGen-software-code-4.0.0/tools
make -f Makefile.suite dsdgen dsqgen
cd /mnt/c/Users/Regina/TPCDS
```

### Generate and load smaller data factors

From the repository root:

```bash
cd /mnt/c/Users/Regina/TPCDS
REFERENCE_SCALE_GB=10 bash scripts/04_generate_scale_data.sh 0.1 0.2 0.5
```

The script generates each factor with TPC-DS `dsdgen` when its `.dat` files are absent, creates a DuckDB database using the supplied TPC-DS schema, and loads the files. At the default reference size, the factors use databases `duckdb/tpcds_sf1.duckdb`, `duckdb/tpcds_sf2.duckdb`, and `duckdb/tpcds_sf5.duckdb`; factor `0.1` maps to 1 GB, so existing files generated with `dsdgen -scale 1 -dir .../data/sf1` are reused. If the SF1 database does not yet exist, the script loads those existing files into `duckdb/tpcds_sf1.duckdb` without regenerating them. Data files are placed in corresponding `data/sf1/`, `data/sf2/`, and `data/sf5/` directories. Its append-only generation log is `results/data_generation.csv`, including total generation-and-load time and artifact sizes.

The default factors omit 1.0 because generating the reference dataset can be expensive (10 GB with the default). Add `1.0` to generate it if your computer can handle it. To rebuild a factor, set `FORCE=1`; that replaces the generated data and database for the corresponding physical scale. Use the same `REFERENCE_SCALE_GB` value when generating data and running the benchmark.

The data-generation script enables `dsdgen` progress output by default, showing which table is being written and periodic progress for large tables. To suppress it, set `DSDGEN_VERBOSE=N`. To leave generation running in the background and watch its log from another WSL terminal:

```bash
cd /mnt/c/Users/Regina/TPCDS
nohup bash scripts/04_generate_scale_data.sh 0.2 0.5 > results/data_generation.log 2>&1 &
echo $! > results/data_generation.pid
tail -f results/data_generation.log
```

Press `Ctrl+C` to stop following the log; this does not stop the generator. Check whether it is still running with `ps -p "$(cat results/data_generation.pid)" -o pid,etime,%cpu,%mem,stat,cmd`, and review the final exit code with `wait "$(cat results/data_generation.pid)"` only in the shell that launched it. Check the generated file sizes from another terminal with `watch -n 5 'du -sh data/sf2 data/sf5 2>/dev/null; ls -lh duckdb/tpcds_sf2.duckdb duckdb/tpcds_sf5.duckdb 2>/dev/null'`. The database files appear and grow during the subsequent DuckDB loading phase.

### Run the query benchmark at each factor

```bash
REFERENCE_SCALE_GB=10 bash scripts/05_run_scale_benchmarks.sh 0.1 0.2 0.5
```

Query generation creates a separate workload for each physical scale: `queries/sf1/`, `queries/sf2/`, `queries/sf4/`, and `queries/sf8/`. The benchmark uses a matching scale-specific workload when present; for other scales it falls back to `queries/all_templates/`. The latter remains a copy of the SF1 workload for compatibility.

```bash
bash scripts/01_generate_queries.sh
```

The command above regenerates queries for all four scales. To generate only selected scales, pass whole-number GB values, for example `bash scripts/01_generate_queries.sh 2 8`. To use a single scale through the legacy environment variable, set `SCALE=4`.

For each scale, the runner keeps one DuckDB CLI process open while it runs all queries. It first completes each warmup pass across the entire query set, then completes each measured pass across the entire set, in ascending query-number order. This makes each measured iteration a full workload round rather than grouping repetitions by query. The queries share DuckDB's in-process buffer cache; warmups are excluded from metrics, and the default is one warmup pass. If a query times out and DuckDB must restart, each query is warmed in the restarted process before its next measurement. Each invocation creates a timestamped directory under `results/benchmark_runs/`. To benchmark the reference scale too, first generate it and then add `1.0` to the runner's factor list. The directory contains:

- `query_metrics.csv`: one row per measured query execution, with factor, query, iteration, status, elapsed wall time, user/system CPU time, peak resident memory, exit code, error summary, database size, SQL file, and log path.
- `summaries/query_summary_sf1.csv`, `summaries/query_summary_sf2.csv`, etc.: separate per-scale summary CSVs with per-query status counts and median/mean elapsed time and CPU time across successful measured runs.
- `metadata.txt`: run settings and machine/DuckDB details.
- `logs/`: individual DuckDB output and errors per query run.

For one warmup and five measured executions of each query:

```bash
REPEATS=5 WARMUP_RUNS=1 REFERENCE_SCALE_GB=10 bash scripts/05_run_scale_benchmarks.sh 0.1 0.2 0.5
```

Warmup passes are excluded from measured rows and summary statistics. Set `WARMUP_RUNS` to change the number of full-workload warmup passes (or `0` to disable them), and adjust the per-execution timeout with `TIMEOUT_SECONDS=600`. A timeout restarts DuckDB; the runner warms each query in the new process before measuring it. Benchmark time and memory measurements are machine- and cache-dependent; keep the same machine, configuration, query order, and run conditions when comparing factors.

### Plot benchmark results

Generate charts and a sortable CSV from a completed benchmark run:

```bash
python3 scripts/plot_benchmark_results.py results/benchmark_runs/<run_id>
```

The script reads the run's `summaries/query_summary_sf<scale>.csv` files and writes its output to `<run_dir>/plots/` by default. Open `plots/index.html` for a report containing:

- A small-multiple grid with one runtime trend per query across the selected factors. Each panel uses its own y-axis to make changes in that query visible; use the ranked charts for absolute time comparisons.
- One fastest-to-slowest query ranking chart per scale. Queries without a successful median are shown after timed queries.
- An estimated workload-time chart, calculated by summing per-query medians that are available; check the execution-outcomes chart to see whether any queries failed or timed out.
- An execution-outcomes chart and `ranked_queries.csv` with exact per-query median times, run counts, failures, and timeouts.

The chart generator uses only the Python standard library and writes SVG, HTML, and CSV files.

### Save query plans for each scale

Run one full workload warm-up round, then save `EXPLAIN` and `EXPLAIN ANALYZE` for every query against each selected scale's DuckDB database:

```bash
REFERENCE_SCALE_GB=10 python3 scripts/explain_duckdb_queries.py --warmup-rounds 1 0.1 0.2 0.4 0.8
```

If no factors are provided, the script uses `0.1 0.2 0.5`. It converts each factor to its physical scale using `REFERENCE_SCALE_GB`, selects the matching query from `queries/sf<scale>/` when available (otherwise using `queries/all_templates/`), and connects to `duckdb/tpcds_sf<scale>.duckdb`. It executes each query once in ascending query-number order as a complete warm-up pass, then captures both plan modes in the same persistent DuckDB session. Warm-up executions and plan captures are recorded separately; `EXPLAIN ANALYZE` also executes its query and can take significant time. Set `TIMEOUT_SECONDS=600` (or another positive number) to change the per-statement timeout. A timeout ends plan collection for that scale rather than restarting without a new warm-up.

Each run creates a timestamped directory under `results/explain_runs/` with `sf<scale>/query<number>.explain.txt` and `sf<scale>/query<number>.explain_analyze.txt` files. `warmup_results.csv` records warm-up round, query execution position, status, and elapsed time. `explain_results.csv` records the warm-up status, DuckDB version, session ID, status, elapsed time, source query, and output path for each plan operation. `metadata.txt` describes the warm-up and collection order.

To combine the per-query outputs into two documents in each scale directory, pass the run directory to:

```bash
python3 scripts/combine_explain_outputs.py results/explain_runs/20261023_140001_315347
```

This creates `combined_explain.txt` and `combined_explain_analyze.txt` in each `sf<scale>/` directory. Query sections are sorted numerically and labeled with their original filenames. The script reports a warning if the run has different numbers of output files for the two modes.

Parse the per-query plans and create CSV/JSON diagnostics in the run's `plan_analysis/` directory:

```bash
python3 scripts/duckdb_plan_analysis.py results/explain_runs/<run_id>
```

### Compare estimated and actual operator cardinalities with JSON

For a structured estimate-versus-actual comparison, run the collector inside the project Docker image:

```bash
docker compose run --rm -T --entrypoint python3 tpcds scripts/compare_duckdb_cardinalities.py
```

It discovers available `duckdb/tpcds_sfN.duckdb` databases and uses the matching `queries/sfN/` workload (falling back to `queries/all_templates/`). By default, it warms each scale with one complete query pass, then saves `EXPLAIN (FORMAT JSON)` and an execution JSON profile for each query in the same DuckDB session. The collector requires DuckDB 1.4.3, keeps its outputs in a new `results/cardinality_runs/<timestamp>/` directory, and does not modify the text explain runs or benchmark timing data.

The aggregate `operator_cardinality_comparison.csv` contains one row per operator path. It reports the estimate, actual count, absolute difference, and `estimated_to_actual_ratio` (estimate divided by actual; blank when the actual count is zero). The `estimated_rows` value prefers the estimate on the profiled operator and falls back to the estimate from the JSON EXPLAIN node at the same tree path. `comparison_status` and `match_confidence` flag missing metrics, unmatched paths, operator-type mismatches, and descendants of an unmatched/mismatched node; numeric differences are calculated only if the operator path, its full ancestor path, and normalized operator type match. `SEQ_SCAN` and `TABLE_SCAN` are treated as equivalent DuckDB scan labels.

Raw JSON plans and profiles are stored under each `sfN/json_explains/` and `sfN/json_profiles/` folder. Per-scale comparisons and query summaries are also written to the corresponding `sfN/` folder. `summary.json`, `metadata.txt`, and `warmup_results.csv` report coverage, missing metrics, collection settings, and warm-up executions. Profile timing remains diagnostic only; use the independent benchmark CSVs for performance comparisons. To rebuild comparison CSVs from an existing run’s saved JSON after an analysis-logic change—without rerunning the workload—use:

```bash
docker compose run --rm -T --entrypoint python3 tpcds scripts/compare_duckdb_cardinalities.py --reprocess-run results/cardinality_runs/<run_id>
```

To test a small subset before a full collection, select scales and query IDs explicitly:

```bash
docker compose run --rm -T --entrypoint python3 tpcds scripts/compare_duckdb_cardinalities.py --query-ids 1 --timeout-seconds 120 1
```

### Repository data sources and analysis provenance

The current repository already contains the core evidence needed for a benchmark and plan-analysis workflow:

- Benchmark timings are stored under `results/benchmark_runs/<timestamp>/query_metrics.csv` and per-scale summaries under `results/benchmark_runs/<timestamp>/summaries/query_summary_sfN.csv`.
- Each measured row keeps `factor`, `scale_gb`, `query`, `iteration`, latency, CPU time, memory, exit code, and the SQL/log paths, so benchmark analysis can separate warmup from measured rounds and preserve round-based execution order.
- Dual-purpose `EXPLAIN` and `EXPLAIN ANALYZE` outputs live under `results/explain_runs/<timestamp>/sfN/`, with one text plan per query and mode. The repository also includes combined documents per scale, which makes cross-query comparisons easier.
- DuckDB metadata is recorded in `metadata.txt` for each run and includes the exact DuckDB version, platform, CPU count, factor list, and timeout settings. This keeps benchmark results traceable and prevents silently mixing incompatible environments.
- The planned analysis pipeline is implemented in `scripts/duckdb_plan_analysis.py`, which conservatively extracts operator names and any row/timing metrics from the text plans, writes a file-level diagnostics CSV, and saves an operator-level summary CSV. It explicitly marks partial or failed parses instead of fabricating missing information.

This separation matters because benchmark timings and profile timings are different measurements. The benchmark CSVs are the authoritative source for wall-clock performance comparisons, while the explain outputs are diagnostic only and should not be added to the benchmark metrics without an explicit provenance label.


DELETE
Command to see all plots in terminal
cd /mnt/c/Users/Regina/TPCDS
explorer.exe "$(wslpath -w results/benchmark_runs/20261023_164300_814393/plots/index.html)"