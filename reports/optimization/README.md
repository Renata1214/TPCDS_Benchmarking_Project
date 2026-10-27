# TPC-DS Query Optimization Results

## Scope

Four TPC-DS queries (Q23, Q39, Q59, and Q95) were evaluated
using DuckDB at scale factor 1 (SF1).

The original and optimized SQL snapshots are stored in:
- `queries/optimization/original/`
- `queries/optimization/optimized/`

## Environment and timing method

- Engine: DuckDB v1.4.3
- Dataset: TPC-DS SF1 validation database
- Runs: one warm-up followed by five measured runs per version
- Warm-up excluded from reported medians
- Execution timing: DuckDB CLI statement-level `real` timings
- For queries containing multiple statements, statement times were
  summed for each run before calculating the median.

The statement-level timings are rounded by DuckDB. In particular,
small differences for fast queries should be interpreted cautiously.

## Median execution-time results

| Query | Original (s) | Optimized (s) | Speedup | Runtime reduction |
|---|---:|---:|---:|---:|
| Q23 | 0.104 | 0.064 | 1.625x | 38.5% |
| Q39 | 0.050 | 0.026 | 1.923x | 48.0% |
| Q59 | 0.031 | 0.030 | 1.033x | 3.2% |
| Q95 | 0.058 | 0.013 | 4.462x | 77.6% |

Speedup is calculated as original median divided by optimized median.
Runtime reduction is calculated as 100 * (1 - optimized/original).

## Correctness checks

The saved result comparisons were rerun against the SF1 validation
database.

- Q23 statement 1: one row from each version; exact comparison matched.
- Q23 statement 2: both versions returned zero rows.
- Q39 statement 1: 176 rows from each version. Exact multiset comparison
  reported eight rows unique to each version. A separate comparison
  matched all 176 key pairs, found no unmatched keys, and found no
  numeric differences greater than 1e-9. Report this as equivalent
  within the chosen numeric tolerance, not bit-for-bit identical.
- Q39 statement 2: five rows from each version; exact comparison matched.
- Q59 statement 1: 100 rows from each version; exact comparison matched.
- Q95 statement 1: one row from each version; exact comparison matched.

Q23 statement 2 returning no rows in either version is evidence for
this tested dataset, not proof that the queries are equivalent for all
possible datasets.

## Interpretation

Q23, Q39, and especially Q95 improved in the measured SF1 runs.
Q59 showed only a small difference (3.2%), which may be within
measurement variability. Results are specific to this DuckDB version,
dataset, and execution environment; larger scale factors and repeated
runs may produce different relative performance.
