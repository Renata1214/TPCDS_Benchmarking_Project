# TPC-DS Query Optimization Results

## Scope

Four TPC-DS queries (Q23, Q39, Q59, and Q95) were evaluated
using DuckDB at SF1, SF2, SF4, and SF8.

The original and optimized SF1 SQL snapshots are stored in:
- `queries/optimization/original/`
- `queries/optimization/optimized/`

The optimized `.tpl` files in `query_templates_optimized/` are the source
of truth. `scripts/generate_optimized_queries.sh` combines them with the
official templates for the other 95 queries and can generate all 99 queries.
The original templates and baseline SQL snapshots are unchanged. No
optimized template or SQL uses an explicit `MATERIALIZED` hint.

## Environment and timing method

- Engine: DuckDB Python 1.5.6 (`.venv-benchmark`)
- Datasets: the same local TPC-DS SF1, SF2, SF4, and SF8 databases for both versions
- Runs: one warm-up followed by five measured runs per version
- Warm-up excluded from reported medians
- Execution timing: Python wall clock around execution and fetching all rows
- Timing order alternates original/optimized by repetition
- Speedup: original median divided by optimized median

The original baseline benchmark in the main report used DuckDB CLI 1.4.3
and a different runner; do not combine its timings with this comparison.

## Median execution-time results

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

Speedups are computed using unrounded medians; displayed medians are rounded
to six decimals and speedups to three, so displayed ratios can differ by 0.001.

## Correctness checks

The final CSV contains 16 query/scale comparisons; all have status `OK`
and `results_match=True`. Comparisons require equal row counts and match each
row against one unmatched row, preserving duplicate multiplicity. Numeric
values use absolute and relative tolerances of 1e-9.

- Q23 statements 1 and 2 matched at all scales; statement 2 returned zero rows at SF1 and SF4.
- Both Q39 statements matched at all four scales within the numeric tolerance.
- Q59 returned 100 matching rows at all scales.
- Q95 returned one matching row at all scales.

Q23 statement 2 returning zero rows is evidence for these tested datasets,
not proof that the queries are equivalent for all data or parameters.

## Interpretation

The reported medians show improvements for all four queries across the
tested scales, with modest changes in some cases and larger changes for Q95.
Results are specific to this DuckDB version, datasets, SQL parameters, and
execution environment. No plan statistics were collected; timings do not
isolate individual rewrite effects. The CSV does not itself persist the
engine version, although the comparison script now writes that field on
future runs.
