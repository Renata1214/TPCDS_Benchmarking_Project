# TPC-DS SF1 results — DuckDB

## Scope

This directory contains preliminary DuckDB timings for TPC-DS scale factor 1
(SF1), along with a diagnostic report for Query 25.

## Timing methodology

- Each listed query or variant was executed five times.
- Repeated executions ran in the same DuckDB process.
- The reported median is the median of the five elapsed times.
- Warm-up and caching may affect repeated executions.
- These are preliminary measurements, not official TPC-DS benchmark scores
  or a fully validated performance comparison.

## SQL files

Adapted SQL files for Queries 25–50 are in `../../queries/sf1/`.
Query 39 has two additional variant files: `query39a.sql` and `query39b.sql`.

These adapted queries should be compared with the original TPC-DS templates
before their results are treated as correctness-validated.

## Result validation

The timing CSV marks result validation as Pending. Successful execution
without a SQL error does not prove semantic correctness. Queries returning
zero rows require investigation against the query specification and dataset.

Query 25's diagnostic findings are in `query25_summary.txt`. The investigation
found no matching customer/item catalog-sales record in the required period
in the tested dataset. This explains the observed zero-row result but does
not, by itself, prove full query correctness.

## Query 39 variants
cat > reports/sf1/README.md <<'EOF'
# TPC-DS SF1 results — DuckDB

## Scope

This directory contains preliminary DuckDB timings for TPC-DS scale factor 1
(SF1), along with a diagnostic report for Query 25.

## Timing methodology

- Each listed query or variant was executed five times.
- Repeated executions ran in the same DuckDB process.
- The reported median is the median of the five elapsed times.
- Warm-up and caching may affect repeated executions.
- These are preliminary measurements, not official TPC-DS benchmark scores
  or a fully validated performance comparison.

## SQL files

Adapted SQL files for Queries 25–50 are in `../../queries/sf1/`.
Query 39 has two additional variant files: `query39a.sql` and `query39b.sql`.

These adapted queries should be compared with the original TPC-DS templates
before their results are treated as correctness-validated.

## Result validation

The timing CSV marks result validation as Pending. Successful execution
without a SQL error does not prove semantic correctness. Queries returning
zero rows require investigation against the query specification and dataset.

Query 25's diagnostic findings are in `query25_summary.txt`. The investigation
found no matching customer/item catalog-sales record in the required period
in the tested dataset. This explains the observed zero-row result but does
not, by itself, prove full query correctness.

## Query 39 variants

- `query39a.sql` is the base variant.
- `query39b.sql` adds the condition `inv1.cov > 1.5`.
- Each variant was executed five times in one DuckDB process.
- Recorded median elapsed times are 0.026 seconds for 39a and 0.022 seconds
  for 39b.

These timings are not a controlled comparison of equivalent queries because
the added filter changes the query's results and potentially its execution
work. The files are retained separately for reproducibility.
