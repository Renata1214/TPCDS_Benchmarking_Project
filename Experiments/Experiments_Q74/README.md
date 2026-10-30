# Query 74 benchmark

Use the shared `../run_benchmark.py` entry point to compare Q74, as with the
other experiment directories.

Run from the Query 74 experiment folder in WSL:

```bash
cd /mnt/c/Users/Regina/TPCDS/Experiments/Experiments_Q74
python3 ../run_benchmark.py \
  --baseline q74_nochanges.sql \
  --experiment q74_experiment1.sql \
  --name q74
```

Defaults are SF1, two warm-ups, ten measured executions per version, Docker
Compose, and a 1800-second per-query timeout. For example:

```bash
python3 ../run_benchmark.py \
  --baseline q74_nochanges.sql \
  --experiment q74_experiment1.sql \
  --name q74 \
  --scale-gb 1 --warmups 2 --repeats 10
```

The universal script extracts the query from `q74_experiment1.sql`, writes a
separate benchmark input that sets `disabled_optimizers` to
`join_order,build_side_probe_side` before the query, and restores the setting
to empty afterward. It does not modify either source SQL file.

The shared runner first compares baseline and experiment output rows as
multisets, ignoring row order but preserving duplicate counts. It stops before
timing if results differ. If they match, it warms both versions, then measures
them in alternating order in one persistent DuckDB session. The warm-ups and
correctness-check timings are not included in the benchmark summary.

Each run creates a unique timestamped results folder here. It contains the
generated benchmark SQL and run metadata, plus a `benchmark/` folder with
result validation, raw measurements, summary statistics, and DuckDB run
metadata. Setup/reset overhead is included in Experiment 1 measured
wall-clock times. Existing results are never overwritten. For warmed EXPLAIN
ANALYZE, run
`python3 ../run_explain_analyze.py q74_experiment1.sql --scale-gb 1 --warmups 1`.

The older `run_q74_benchmark.py` remains as a compatibility shortcut; it
delegates to the same universal runner.
