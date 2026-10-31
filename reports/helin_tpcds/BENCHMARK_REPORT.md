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
`queries/optimization/`. The optimized SQL is generated from the four
optimized `.tpl` files combined with the official templates for the other
95 queries. These experiments cover SF1, SF2, SF4, and SF8 and are separate
from the original cross-scale benchmark in Sections 3–5.

### Optimization approach

- **Q23:** Combines customer sales into one customer-level aggregate for
   total sales and period sales, uses a window maximum to identify the
   qualifying threshold, removes the item description from the frequent-item
   grouping key, and applies the item/customer filters after combining sales
   channels. The narrower grouping and consolidated logical aggregation may
   reduce intermediate work; the report does not claim a particular physical
   plan or forced CTE materialization.
- **Q39:** Restricts inventory aggregation to the two requested months and
   groups by warehouse key rather than carrying warehouse name through the
   intermediate aggregate. This can reduce input rows and grouping width.
- **Q59:** Uses aggregate `FILTER` clauses for weekday sales and restricts
   the weeks entering the aggregate to the query's selected month range.
   This can reduce conditional-expression and aggregation work.
- **Q95:** Replaces the `web_sales` order self-join with a per-order
   `MIN`/`MAX` warehouse check, avoiding pair generation for orders with
   multiple sales rows. The returns check is expressed as direct order
   membership.

No optimized template or generated query uses an explicit `MATERIALIZED`
hint or materialized table. The original templates and original SQL
snapshots remain the baseline.

### Experimental setup and methodology

- Engine for the comparison: DuckDB Python 1.5.6 in the selected
   `.venv-benchmark` environment. The original cross-scale benchmark above
   used DuckDB CLI 1.4.3; its timings are a separate dataset of measurements.
- Databases: the same local TPC-DS SF1, SF2, SF4, and SF8 databases for each
   original/optimized pair.
- Each pair was validated and timed through one read-only DuckDB connection.
   The timed operation includes execution and fetching all result rows for
   every statement in the query.
- One warm-up per version was excluded from five measured runs. The order
   alternated by repetition: original then optimized, followed by optimized
   then original, and repeated.
- Each reported time is the median of the five end-to-end measured runs.
   Speedup is original median divided by optimized median. The CSV stores
   medians to six decimals and speedups to three decimals; speedups are
   calculated from unrounded timings, so a ratio of displayed medians can
   differ by 0.001 after rounding.
- Validation is duplicate-aware multiset comparison: row counts must match,
   each original row must match one still-unmatched optimized row, and numeric
   values use both absolute and relative tolerances of 1e-9.

The selected Python environment reports DuckDB 1.5.6, and the comparison
script prints the engine version when run. The saved CSV does not itself
contain a version column; the script has been updated so future output
records the version for every row.

### Final optimization comparison

All 16 query/scale comparisons in
`reports/optimization/four_queries_final.csv` have status `OK` and
`results_match=True`.

| Scale | Query | Original median (s) | Optimized median (s) | Speedup |
|---|---:|---:|---:|---:|
| SF1 | Q23 | 0.061492 | 0.049405 | 1.245x |
| SF1 | Q39 | 0.024609 | 0.021064 | 1.168x |
| SF1 | Q59 | 0.030368 | 0.015459 | 1.964x |
| SF1 | Q95 | 0.043171 | 0.006687 | 6.456x |
| SF2 | Q23 | 0.108043 | 0.087126 | 1.240x |
| SF2 | Q39 | 0.026124 | 0.023758 | 1.100x |
| SF2 | Q59 | 0.036718 | 0.030474 | 1.205x |
| SF2 | Q95 | 0.051638 | 0.009393 | 5.498x |
| SF4 | Q23 | 0.210513 | 0.148325 | 1.419x |
| SF4 | Q39 | 0.040675 | 0.030481 | 1.334x |
| SF4 | Q59 | 0.060722 | 0.048957 | 1.240x |
| SF4 | Q95 | 0.088965 | 0.013440 | 6.619x |
| SF8 | Q23 | 0.491021 | 0.304439 | 1.613x |
| SF8 | Q39 | 0.079402 | 0.057173 | 1.389x |
| SF8 | Q59 | 0.089895 | 0.066455 | 1.353x |
| SF8 | Q95 | 0.168389 | 0.024095 | 6.989x |

### Correctness and interpretation

The validation details are recorded per statement in the CSV. Q23 has two
statements; its second statement returns zero rows on SF1 and SF4, so those
cases demonstrate agreement only for the tested databases. Q39 has two
statements and both matched at every scale. Q59 and Q95 each have one
statement and matched at every scale. These results validate only the saved
SQL and datasets tested; they do not prove equivalence for all possible
datasets or generated parameter values.

All four queries were faster in these measurements. Q39's SF2 improvement
was modest (1.100x), while Q95 showed the largest measured speedups. These
are environment-specific timings, not official TPC-DS scores or guarantees.
No execution-plan statistics were collected for this comparison, and the
measurements do not isolate the effect of individual rewrite components.

The optimization comparison must not be mixed with the baseline benchmark
measurements in Sections 3–5: the engine version, timing harness, repetitions,
and measured query workload differ. Detailed rewrite notes are in
`reports/helin_tpcds/QUERY_OPTIMIZATION_NOTES.md`.

## 7. Limitations and outstanding work

1. SF5 completed with all 99 queries measured three times. Its summary was
   reconstructed from raw metrics because DuckDB did not shut down normally.
   SF10 benchmarking remains pending.
2. SF8 Q22 has no measured result because its warm-up failed.
3. The optimization comparison covers only four queries at SF1, SF2, SF4,
   and SF8; the other 95 queries have not yet been optimized in this project.
4. Runtime results depend on the environment, memory availability, DuckDB
   settings, and workload state.
5. The current results are measurements from this environment, not universal
   performance guarantees.

## 8. Conclusion

The original run provides three-repetition measurements for SF1, SF2, and SF4,
plus partial query coverage at SF8. The separate SF5 run adds three measured
repetitions for all 99 queries, although its summary had to be reconstructed
because DuckDB stalled during shutdown. SF10 remains outstanding, so the full
intended scale-factor set has not yet been evaluated. In the separate
four-scale optimization comparison, all four assigned queries improved and
all 16 original-versus-optimized result validations passed.

## 9. Supporting artifacts

- Raw metrics (original four-scale run): `results/benchmark_runs/20261028_110053_343884/query_metrics.csv`
- SF5 raw metrics: `results/benchmark_runs/20261028_115520_962190/query_metrics.csv`
- SF5 reconstructed summary: `results/benchmark_runs/20261028_115520_962190/summaries/query_summary_sf5.csv`
- Run metadata: `results/benchmark_runs/20261028_110053_343884/metadata.txt`
- Cross-scale summary: `results/benchmark_runs/20261028_110053_343884/summaries/cross_scale_comparison.csv`
- Per-scale summaries: `results/benchmark_runs/20261028_110053_343884/summaries/`
- Optimization methodology and outputs: `reports/optimization/`
