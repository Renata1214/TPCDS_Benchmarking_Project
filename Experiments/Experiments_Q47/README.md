# Query 47 experiment

This folder contains the baseline and Experiment 1 SQL, prior explain output,
and historical Query 47 benchmark runs.

From this directory in WSL, run the shared benchmark:

```bash
python3 ../run_benchmark.py \
  --baseline query47_noChanges.sql \
  --experiment query47_Experiment1.sql \
  --name q47
```

Get a warmed EXPLAIN ANALYZE plan for one variant:

```bash
python3 ../run_explain_analyze.py query47_Experiment1.sql --scale-gb 1 --warmups 1
```

See `../README.md` for options, benchmark procedure, and output descriptions.
