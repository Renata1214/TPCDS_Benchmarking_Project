# Reproducing the TPC-DS work completed so far

This guide records the repository workflow, the effects of Docker, the current state of the generated artifacts, and the steps to finish and reproduce the work. It covers the TPC-DS portion only; it is not a completed TPC-DI implementation or an official TPC benchmark audit.

## What this project currently does

The current workflow has three main stages:

1. Generate SQL from the TPC-DS query templates for a physical scale, using the DuckDB dialect.
2. Generate the TPC-DS `.dat` files for that scale, create a DuckDB database from `tools/tpcds.sql`, and load the files into that database.
3. Run each generated query against the corresponding database, recording timings, statuses, resource measurements, logs, and per-scale summaries.

With `REFERENCE_SCALE_GB=10`, a relative factor maps to these physical scales:

| Relative factor | Physical scale | Raw data directory | DuckDB database | Query directory |
|---:|---:|---|---|---|
| `0.1` | 1 GB | `data/sf1/` | `duckdb/tpcds_sf1.duckdb` | `queries/sf1/` |
| `0.2` | 2 GB | `data/sf2/` | `duckdb/tpcds_sf2.duckdb` | `queries/sf2/` |
| `0.4` | 4 GB | `data/sf4/` | `duckdb/tpcds_sf4.duckdb` | `queries/sf4/` |
| `0.8` | 8 GB | `data/sf8/` | `duckdb/tpcds_sf8.duckdb` | `queries/sf8/` |
| `1.0` | 10 GB | `data/sf10/` | `duckdb/tpcds_sf10.duckdb` | `queries/sf10/` |

The data generator accepts whole-number GB scales. Use factors whose product with the reference scale is a whole number of at least 1.

## What Docker changes, and what it does not

The Docker files provide a Debian-based environment, DuckDB CLI version 1.4.3 by default, and Linux TPC-DS generator executables. Docker Compose mounts the whole project directory into the container (`.:/workspace`), so files written under `/workspace` are also written into this Windows/WSL project folder and persist after the container exits.

There are two distinct effects:

- `docker compose build` builds the image. It does not, by itself, run the entrypoint against the mounted project.
- `docker compose run` starts the container and runs `docker-entrypoint.sh`. The entrypoint copies the image's `dsdgen` and `dsqgen` executables into `Kit/DSGen-software-code-4.0.0/tools/` in the mounted project. Those are tracked files, so this replaces the local executables and appears in `git status`.

The default Compose command then runs `scripts/run_tpcds.sh`. That can generate or replace query SQL, raw data, databases, and results inside the mounted project. In the current scripts, the query generator creates workloads for physical scales 1, 2, 4, and 8 GB and mirrors SF1 SQL to `queries/all_templates/`. Running the container with a shell instead of the workflow still invokes the entrypoint and replaces the two generator executables first.

The container removal flag (`--rm`) removes the container, **not** files written through the bind mount and not the built image. Docker may also use different CPU, memory, filesystem, and cache settings than native WSL. For comparable measurements, run all scales using the same environment and resource limits.

The changed generator binaries and some changed SQL files are consistent with the container entrypoint and workflow having run, but Git status alone cannot prove which command changed every SQL file. The reason `dsdgen` segfaulted has not been established. The timing of the binary replacement does not prove that Docker caused the crash; do not use the replacement executable for further data generation until it has been checked.

The data-generation script supports `DSDGEN_BIN` so Docker's generator can be used without replacing the local executable. Rebuild the image without cache so the TPC-DS tools are compiled using the image's Debian libraries, then run only the data/load script:

```bash
cd /mnt/c/Users/Regina/TPCDS
docker compose build --no-cache tpcds
docker compose run --rm \
  -e REFERENCE_SCALE_GB=10 \
  -e FORCE=1 \
  tpcds bash scripts/04_generate_scale_data.sh 0.4
```

The image sets `DSDGEN_BIN` to its freshly compiled `/usr/local/bin/dsdgen`. Its entrypoint no longer copies the container tools into the mounted project. `FORCE=1` is required because the existing SF4 files are incomplete. Never run this at the same time as another process writing to SF4.

## State recorded on 2026-10-21

This is a snapshot, not a live status check. Check the actual files and processes before following recovery commands.

| Scale | Raw files observed | Database observed | State |
|---|---:|---|---|
| SF1 | 25/25 | `tpcds_sf1.duckdb` present | Generated and loaded |
| SF2 | 25/25 | `tpcds_sf2.duckdb` present | Generated and loaded |
| SF4 | 23/25 named files | No SF4 database | **Incomplete**. `web_sales.dat` and `web_returns.dat` were present after an interrupted generation, but their contents cannot be assumed complete; `web_site.dat` and `dbgen_version.dat` were missing. |
| SF8 | 11/25 files at the last check | No SF8 database | **In progress**. WSL process PID `87682` was generating SF8. |

The presence of a non-empty `.dat` file does not prove it is complete. Only treat a scale as ready after `dsdgen` exits successfully and all expected data files are present. A database is ready only after the loading script finishes successfully.

At that snapshot, the scale-specific SQL directories contained 99 official `query<number>.sql` files for SF2, SF4, and SF8. SF1 contained those plus a pre-existing `query_0.sql`; the benchmark runner accepts that filename as well. For strictly comparable reports, check that each scale uses the same intended query set before benchmarking. Regenerating with `scripts/01_generate_queries.sh 1 2 4 8` creates the current scale-specific workload; it overwrites SQL files in those scale directories and rewrites the legacy SF1 copy in `queries/all_templates/`.

## Safe recovery of the current data

1. **Do not run two generators against the same scale at once.** Check for active generators from WSL:

   ```bash
   pgrep -af dsdgen
   ```

   Let the existing SF8 process finish. Do not replace the generator executable while it is running.

2. **Check SF8 after the process exits.** Confirm it exited successfully and that all 25 expected `.dat` files exist and are non-empty. If generation was interrupted or failed, the current script has no resumable checkpoint: regenerate SF8 completely after confirming no other generator is writing to it:

   ```bash
   cd /mnt/c/Users/Regina/TPCDS
   REFERENCE_SCALE_GB=10 FORCE=1 bash scripts/04_generate_scale_data.sh 0.8
   ```

3. **Restore the committed generators only after all `dsdgen` processes have stopped**, if the committed binaries are the downloaded versions you want to use. This restores only those two tracked files:

   ```bash
   cd /mnt/c/Users/Regina/TPCDS
   git restore -- Kit/DSGen-software-code-4.0.0/tools/dsdgen Kit/DSGen-software-code-4.0.0/tools/dsqgen
   ```

   `git restore` replaces the working copies with the repository's committed versions. Check `git status` first and do not use this if you have a different local binary you need to keep.

4. **Regenerate SF4 completely.** The previous SF4 generation was interrupted, and table-only `dsdgen` attempts segfaulted with the current executable. Do not rely on the resulting partial files. After the generator binary has been verified and no generator is running:

   ```bash
   cd /mnt/c/Users/Regina/TPCDS
   REFERENCE_SCALE_GB=10 FORCE=1 bash scripts/04_generate_scale_data.sh 0.4
   ```

   This replaces SF4 raw files and its SF4 database only. If `dsdgen` segfaults again, stop and keep the error output; do not continue to benchmark SF4.

5. **Load SF8 after its raw data is complete.** If generation finished outside the scale script and the database does not yet exist, run the scale script without `FORCE`:

   ```bash
   cd /mnt/c/Users/Regina/TPCDS
   REFERENCE_SCALE_GB=10 bash scripts/04_generate_scale_data.sh 0.8
   ```

   If the scale script itself completed successfully, do not load it again.

Avoid running the generation script concurrently with Docker or another WSL generation command. In particular, never run two commands that target the same `data/sfN/` directory or DuckDB database.

## Step-by-step reproduction

### 1. Record the code and environment

Keep a copy of the current project before restoring binaries or regenerating query files. Record:

```bash
git status --short
git diff --stat
docker compose config
docker --version
docker compose version
```

For a reproducible submission, commit or archive the source scripts, Docker configuration, query SQL used for the run, and a record of the exact generator and DuckDB versions. Do not package incomplete raw datasets as if they were finished.

### 2. Choose one execution environment

Use either Docker or WSL for a benchmark series; do not switch environments between scales. Docker provides pinned DuckDB CLI version 1.4.3 by default, but its entrypoint currently copies its compiled generator binaries into the project. WSL uses whatever Linux `dsdgen`, `dsqgen`, and DuckDB CLI are installed there. Record which path was used and all versions.

The Docker command is:

```bash
cd /mnt/c/Users/Regina/TPCDS
docker compose build
```

Do not run `docker compose run` concurrently with WSL generation. Each container invocation runs the entrypoint, so it also replaces the local generator executables.

### 3. Generate the query workload

When using the scale-specific query generation script:

```bash
cd /mnt/c/Users/Regina/TPCDS
bash scripts/01_generate_queries.sh 1 2 4 8
```

For exact reproduction of an existing benchmark, preserve and reuse the exact SQL files instead of regenerating them with a different `dsqgen` build. Verify the same query filenames are present in each scale directory. In particular, decide whether the non-standard `query_0.sql` in `queries/sf1/` is part of the workload; the current runner recognizes it, while it is not among the 99 official numbered templates.

### 4. Generate and load data scales

Run one scale at a time to simplify monitoring and recovery. For example, SF4 and SF8:

```bash
cd /mnt/c/Users/Regina/TPCDS
REFERENCE_SCALE_GB=10 bash scripts/04_generate_scale_data.sh 0.4
REFERENCE_SCALE_GB=10 bash scripts/04_generate_scale_data.sh 0.8
```

The script reuses complete raw data if the corresponding database is missing, then loads the data into the matching database. If data is incomplete, it stops instead of silently mixing it with another run. `FORCE=1` regenerates all raw files for each requested scale and replaces that scale's database; it does not resume an interrupted run.

For each scale, verify all 25 expected `.dat` files exist and are non-empty, the command exits with status zero, and `duckdb/tpcds_sfN.duckdb` exists. The script appends generation/load timings and byte sizes to `results/data_generation.csv`.

### 5. Run the benchmark

For SF1, SF2, SF4, and SF8:

```bash
cd /mnt/c/Users/Regina/TPCDS
REFERENCE_SCALE_GB=10 REPEATS=5 WARMUP_RUNS=1 \
  bash scripts/05_run_scale_benchmarks.sh 0.1 0.2 0.4 0.8
```

The benchmark keeps one DuckDB process open per scale. Each query is warmed and then measured in that process. Warmup runs are excluded from timing summaries. The timestamped directory under `results/benchmark_runs/` contains:

- `query_metrics.csv`: measured-run metrics and paths.
- `summaries/query_summary_sfN.csv`: one summary CSV per physical scale.
- `logs/sfN/`: DuckDB query output and error logs.
- `metadata.txt`: scale factors, run counts, DuckDB version, and machine details.

The runner records elapsed time, CPU time, sampled resident memory, execution status, timeout/errors, and database size. Results are specific to the machine, filesystem, DuckDB version, query files, and warm-cache setup; this is a course benchmark workflow, not an official TPC-DS result.

### 6. Preserve and interpret results

Keep each timestamped benchmark directory intact and associate it with the exact query SQL, generator binary/version, database scale, Docker/WSL choice, hardware allocation, and run settings. Compare scale summaries only when those conditions are consistent. The report should identify failed and timed-out queries, not silently omit them.

The project deliverables described in `readme.md` are a PDF implementation/results report and a ZIP containing the reproducible source and instructions. Dataset and database files are large; include them only if required, and otherwise document how to regenerate them.

## Current limitations to resolve before final submission

- SF4 and SF8 were incomplete in the recorded snapshot; they must not be reported as completed or benchmarked until successfully regenerated and loaded.
- The `dsdgen` segmentation fault is unresolved. A Docker run and table-only invocation both failed in the observed session; this does not establish the root cause.
- Docker runtime currently replaces the local generator executables through the bind mount. Use one verified tool build consistently and record its version.
- SF1 has an extra `query_0.sql`; normalize the intended query set across scales before comparing results.
- The benchmark runner should be tested end-to-end after the DuckDB CLI is available, including verification that each scale-specific summary contains the expected query count.
