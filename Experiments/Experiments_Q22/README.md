# Query 22 experiment

This folder contains the original and Experiment 1 SQL, plus the prior
benchmark and warmed EXPLAIN ANALYZE outputs.

From this directory in WSL, run the shared benchmark:

```bash
python3 ../run_benchmark.py \
  --baseline query22_original.sql \
  --experiment query22_Experiment1.sql \
  --name q22
```

Get a warmed EXPLAIN ANALYZE plan for one variant:

```bash
python3 ../run_explain_analyze.py query22_Experiment1.sql --scale-gb 1 --warmups 1
```

See `../README.md` for options, benchmark procedure, and output descriptions.
