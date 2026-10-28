# TPC-DS Benchmark Report — DuckDB

**Project:** Data Warehouses (INFO-H-419), ULB
**Prepared by:** Helin Mazi
**Report date:** 28 October 2026
**Engine:** DuckDB 1.4.3 (Andium)
**Benchmark platform:** Linux container, 18 reported CPUs

## 1. Objective

This report documents my DuckDB implementation and benchmarking work for
TPC-DS. It records the benchmark methodology, verified results, optimization
experiments, limitations, and outstanding work.

This is a separate report for my work. The existing `readme.md` and
`REPRODUCING.md` files are intentionally left unchanged.

## 2. Dataset and scale factors

The configured reference scale is 10 GB. The benchmark factor is multiplied
by this reference to obtain the physical scale:

| Factor | Physical scale | Status |
|---:|---:|---|
| 0.1 | SF1 (1 GB) | Benchmark completed |
| 0.2 | SF2 (2 GB) | Benchmark completed |
| 0.4 | SF4 (4 GB) | Additional exploratory benchmark completed |
| 0.5 | SF5 (5 GB) | Completed; summary reconstructed from saved metrics |
| 0.8 | SF8 (8 GB) | Benchmark completed; Q22 warm-up failed |
| 1.0 | SF10 (10 GB) | Database and query files present; benchmark pending |

The required scale set should be evaluated separately from the additional
SF4 and SF8 experiments. SF5 has now been benchmarked and its 297 measured records checked. Its summary
was reconstructed from the saved raw metrics after DuckDB stalled during
shutdown. SF10 remains pending.

All six scale databases and their corresponding query directories were
present when the files were checked on 28 October 2026. Each query directory
contained 99 SQL query files.

## 3. Benchmark methodology

The principal completed run is:

- Run ID: `20261028_110053_343884`
- Output directory: `results/benchmark_runs/20261028_110053_343884/`
- Reference scale: 10 GB
- Factors: 0.1, 0.2, 0.4, 0.8
- Measured repetitions per query: 3
- Warm-up runs per query: 1
- Timeout per execution: 300 seconds
- DuckDB version: 1.4.3
- Warm-up and measured executions used one persistent DuckDB process per scale.

The raw metrics are recorded in `query_metrics.csv`. The run metadata is in
`metadata.txt`, and per-scale summaries are under `summaries/`. The separate
SF5 run is documented below.

Warm-ups are not included as measured repetitions. Query execution times are
reported by the benchmark runner. The median-of-query-medians below is the
median across the per-query median timings; it is a descriptive statistic,
not total workload runtime.

## 4. Completed benchmark results

| Scale | Queries in summary | Successful measured executions | Failed measured executions | Timed-out measured executions | Median of per-query medians |
|---|---:|---:|---:|---:|---:|
| SF1 | 99 | 297 | 0 | 0 | 0.010 s |
| SF2 | 99 | 297 | 0 | 0 | 0.013 s |
| SF4 | 99 | 297 | 0 | 0 | 0.019 s |
| SF5* | 99 | 297 | 0 | 0 | 0.037 s |
| SF8 | 99 | 294 | 0 | 0 | 0.038 s |

The original four-scale run had 1,185 successful measured executions and no
failed or timed-out measured executions. The separate SF5 run added 297
successful measured executions, giving 1,482 successful measured executions
across these five scale-factor runs. SF8 Q22 is an
important exception to query coverage: its warm-up failed, so it has no
measured executions. The SF8 summary therefore contains 99 query rows, but
only 98 queries received all three measured repetitions.

For SF1, SF2, and SF4, all 99 queries completed all three measured
repetitions. Their observed ranges of per-query median timings were:

- SF1: 0.002–0.101 seconds
- SF2: 0.003–0.213 seconds
- SF4: 0.003–0.416 seconds
- SF8: 0.006–3.056 seconds, excluding Q22, which has no measured result
- SF5: 0.005–3.831 seconds

*SF5* is a separate run (`20261028_115520_962190`). Its raw CSV contains 297 `WORKING` measured records (three per query) and no failed or timed-out measured records. The per-query summary was reconstructed from that CSV after the DuckDB process continued consuming CPU after Q99. The recorded query timings were not rerun. The aggregate is the median of the 99 per-query medians, not total workload runtime.

## 5. Scaling observations

The query-level median summaries generally show increasing runtimes at
larger scales, although individual queries do not all behave identically.

Selected query medians, in seconds:

| Query | SF1 | SF2 | SF4 | SF5 | SF8 |
|---|---:|---:|---:|---:|---:|
| Q22 | 0.041 | 0.058 | 0.383 | 3.831 | No measured result |
| Q23 | 0.085 | 0.191 | 0.330 | 0.674 | 1.348 |
| Q39 | 0.037 | 0.046 | 0.086 | 0.297 | 0.315 |
| Q67 | 0.099 | 0.203 | 0.344 | 0.761 | 3.056 |
| Q95 | 0.058 | 0.053 | 0.098 | 0.143 | 0.210 |

These results illustrate why it is useful to report query-level results rather
than only one aggregate figure. Q95, for example, did not become slower from
SF1 to SF2 in this run. The measurements should not be interpreted as a
guarantee of linear scaling.

### SF8 Q22 memory limitation

Q22 failed during its warm-up with an out-of-memory error. The log reported
approximately 6.1 GiB in use and a failure to pin a 256 KiB block. Because
the warm-up failed, the runner skipped measured executions for that query.

A separate targeted test using `SET threads=1` and
`SET preserve_insertion_order=false` succeeded in approximately 1.573 seconds
and returned 100 rows. That test used different settings and is not part of
the official benchmark results; it must not be compared directly with the
main run as if it used the same configuration.

## 6. Query optimization experiments

Four queries were tested using original and optimized SQL snapshots under
`queries/optimization/`. These experiments used the SF1 database and are
separate from the cross-scale benchmark.

### Statement-timing summary

| Query | Original median | Optimized median | Speedup | Time reduction |
|---|---:|---:|---:|---:|
| Q23 | 0.104 s | 0.064 s | 1.625x | 38.5% |
| Q39 | 0.050 s | 0.026 s | 1.923x | 48.0% |
| Q59 | 0.031 s | 0.030 s | 1.033x | 3.2% |
| Q95 | 0.058 s | 0.013 s | 4.462x | 77.6% |

These figures come from the statement-timing method documented in
`reports/optimization/README.md`. Multi-statement timings were summed per
run before calculating medians.

A separate wall-clock measurement produced different speedups:

| Query | Original wall-clock median | Optimized wall-clock median | Speedup |
|---|---:|---:|---:|
| Q23 | 0.130556 s | 0.087777 s | 1.487x |
| Q39 | 0.072818 s | 0.043330 s | 1.681x |
| Q59 | 0.049257 s | 0.048136 s | 1.023x |
| Q95 | 0.075556 s | 0.028380 s | 2.662x |

The two timing methods are reported separately and should not be mixed.
Q23, Q39, and particularly Q95 improved in these experiments. Q59's small
change may be within measurement variability.

### Correctness checks

- Q23: the first statement returned one row for each version with an exact
  match; the second statement returned zero rows for both versions on the
  tested dataset.
- Q39: the first statement returned 176 rows for each version. Exact
  multiset comparison showed differences, but key-pair comparison matched
  all 176 key pairs and found no numeric differences above 1e-9. This
  supports equivalence within the tested tolerance, not bit-for-bit identity.
  The second statement returned five exact matching rows.
- Q59: 100 rows matched exactly.
- Q95: one row matched exactly.

These checks cover the tested SF1 dataset and do not establish correctness
for every possible dataset or scale factor.

Detailed query-by-query optimization changes, their rationale, timing results, and correctness limitations are documented in `reports/helin_tpcds/QUERY_OPTIMIZATION_NOTES.md`.

## 7. Limitations and outstanding work

1. SF5 completed with all 99 queries measured three times. Its summary was
   reconstructed from raw metrics because DuckDB did not shut down normally.
   SF10 benchmarking remains pending.
2. SF8 Q22 has no measured result because its warm-up failed.
3. The optimization experiments cover only four queries at SF1.
4. Runtime results depend on the environment, memory availability, DuckDB
   settings, and workload state.
5. The current results are measurements from this environment, not universal
   performance guarantees.

## 8. Conclusion

The original run provides three-repetition measurements for SF1, SF2, and SF4,
plus partial query coverage at SF8. The separate SF5 run adds three measured
repetitions for all 99 queries, although its summary had to be reconstructed
because DuckDB stalled during shutdown. SF10 remains outstanding, so the full
intended scale-factor set has not yet been evaluated. The query optimization
experiments show encouraging improvements for Q23, Q39, and Q95, while Q59
shows only a small change.

## 9. Supporting artifacts

- Raw metrics (original four-scale run): `results/benchmark_runs/20261028_110053_343884/query_metrics.csv`
- SF5 raw metrics: `results/benchmark_runs/20261028_115520_962190/query_metrics.csv`
- SF5 reconstructed summary: `results/benchmark_runs/20261028_115520_962190/summaries/query_summary_sf5.csv`
- Run metadata: `results/benchmark_runs/20261028_110053_343884/metadata.txt`
- Cross-scale summary: `results/benchmark_runs/20261028_110053_343884/summaries/cross_scale_comparison.csv`
- Per-scale summaries: `results/benchmark_runs/20261028_110053_343884/summaries/`
- Optimization methodology and outputs: `reports/optimization/`
