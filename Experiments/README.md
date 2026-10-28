# TPC-DS query experiments

Each query experiment has its own folder:

- `Experiments_Q22/` — Query 22 original and Experiment 1.
- `Experiments_Q47/` — Query 47 SQL, explain output, and historical benchmark runs.
- `Experiments_Q74/` — Query 74 baseline and Experiment 1 with the forced join order.

Run commands from the experiment folder in WSL. The common utilities live one
directory above each folder and resolve the repository/database paths
independently of the current directory.

## Benchmark any experiment

Use the same `run_benchmark.py` entry point for all experiment folders. Pass
the baseline and experiment SQL file names in that folder:

```bash
cd /mnt/c/Users/Regina/TPCDS/Experiments/Experiments_Q22
python3 ../run_benchmark.py \
  --baseline query22_original.sql \
  --experiment query22_Experiment1.sql \
  --name q22
```

For Query 47:

```bash
cd /mnt/c/Users/Regina/TPCDS/Experiments/Experiments_Q47
python3 ../run_benchmark.py \
  --baseline query47_noChanges.sql \
  --experiment query47_Experiment1.sql \
  --name q47
```

For Query 74:

```bash
cd /mnt/c/Users/Regina/TPCDS/Experiments/Experiments_Q74
python3 ../run_benchmark.py \
  --baseline q74_nochanges.sql \
  --experiment q74_experiment1.sql \
  --name q74
```

The defaults are SF1, two warm-ups, ten measured rounds, Docker Compose, and a
1800-second per-query timeout. Set `--scale-gb`, `--warmups`, `--repeats`,
`--timeout-seconds`, or `--runtime native` to adjust them. The Query 74 SQL
wrapper is recognized automatically: the runner creates a separate benchmark
SQL file that keeps `join_order,build_side_probe_side` disabled for the query
and restores the setting afterward.

The universal runner first compares results as multisets (row order ignored,
duplicate counts preserved). A mismatch stops the run before timing. If
results match, it warms both variants, then alternates their order across
measured rounds in a persistent DuckDB session. Only measured runs contribute
to the summary. If the experiment SQL uses optimizer setup and reset
statements, their small execution overhead is included in that variant's
measured wall time.

Every invocation creates a new timestamped results folder beside the baseline
SQL. It contains `result_validation.csv`, measurements, summary statistics,
metadata, and—when optimizer settings need preprocessing—the generated
benchmark SQL. Existing runs are not overwritten.

`benchmark_runner.py` is the shared timing engine. Normally, use
`run_benchmark.py` so experiment SQL requiring preprocessing is handled
consistently.

## EXPLAIN ANALYZE any experiment SQL

From any experiment folder, run the common plan utility with a SQL file in that
folder:

```bash
cd /mnt/c/Users/Regina/TPCDS/Experiments/Experiments_Q74
python3 ../run_explain_analyze.py q74_experiment1.sql --scale-gb 1 --warmups 1
```

For Query 22 or Query 47, substitute the desired SQL file, for example
`query22_Experiment1.sql` or `query47_Experiment1.sql`. The utility accepts
SQL with or without a leading `EXPLAIN ANALYZE`. It also recognizes the Q74
optimizer setup/reset wrapper, executes the warm-up and plan in the same
DuckDB session, then restores and verifies the setting after plan capture.
Output and metadata are saved to a new timestamped folder next to the input SQL.

Docker Compose and the project DuckDB 1.4.3 image are used by default. Choose a
database with `--scale-gb 1`, `2`, `4`, or `8`. Close any interactive DuckDB
session that is holding the selected database before running; the utilities do
not interrupt existing sessions.
