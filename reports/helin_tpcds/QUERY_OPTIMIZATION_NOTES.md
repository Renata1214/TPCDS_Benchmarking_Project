# TPC-DS Query Optimization Notes

**Engine:** DuckDB 1.4.3
**Dataset:** TPC-DS scale factor 1 (SF1)
**Queries:** Q23, Q39, Q59, Q95

## 1. Overview

The original and optimized SQL snapshots are preserved separately in
`queries/optimization/original/` and `queries/optimization/optimized/`.
The changes below are based on a diff of those files.

The aim was to reduce unnecessary aggregation work, intermediate
grouping, and join work while retaining the query's intended results.
Performance and correctness were evaluated on the tested SF1 database;
these checks do not prove equivalence for every possible dataset.

## 2. Q23 — Reuse customer-level aggregates

### Changes

The optimized query introduces a materialized `cust_sales` CTE. It
calculates total sales and sales within the specified four-year period
for each customer. The maximum period-specific sales is then obtained
from this CTE, and the qualifying customer set reuses the same
customer-level aggregates.

The frequent-item CTE is also materialized. Its grouping no longer
includes `substr(i_item_desc, 1, 30)`, retaining the item key and date
grouping instead.

### Rationale

The original SQL separately aggregates store sales to determine the
maximum period-specific customer sales and the total sales of
qualifying customers. Reusing the customer-level aggregate can avoid
repeating that work. Simplifying the frequent-item grouping can also
reduce intermediate grouping work.

These benefits depend on DuckDB's execution plan and the data. The
runtime measurements show the result, but do not isolate the contribution
of each individual change.

### Results and validation

- Statement-timing median: 0.104 s original; 0.064 s optimized.
- Speedup: 1.625x; runtime reduction: 38.5%.
- Wall-clock median: 0.130556 s original; 0.087777 s optimized.
- Correctness: the first statement returned one matching row per
  version. The second returned zero rows for both versions on SF1.

The zero-row result is evidence for this test dataset, not proof of
equivalence on all datasets.

## 3. Q39 — Restrict inventory aggregation to relevant months

### Changes

The optimized `inv` CTE filters `d_moy` to months 1 and 2 before
calculating the sample standard deviation and average inventory
quantity. It also removes warehouse name from the intermediate
selection and grouping, retaining the warehouse key used downstream.

### Rationale

The final comparison concerns January and February. Restricting the
input to those months before aggregation can reduce the number of
inventory rows processed. Removing a grouping attribute that is not
needed by the downstream query can simplify the intermediate grouping.

### Results and validation

- Statement-timing median: 0.050 s original; 0.026 s optimized.
- Speedup: 1.923x; runtime reduction: 48.0%.
- Wall-clock median: 0.072818 s original; 0.043330 s optimized.
- Correctness: the first statement returned 176 rows per version.
  Exact multiset comparison found differences, but a separate comparison
  matched all 176 key pairs, found no unmatched keys, and found no
  numeric differences above 1e-9. This supports equivalence within the
  tested tolerance, not bit-for-bit identity.
- The second statement returned five matching rows.

## 4. Q59 — Filtered aggregates and a narrower week range

### Changes

The optimized query replaces seven conditional expressions of the form
`SUM(CASE WHEN day_name = ... THEN sales_price ELSE NULL END)` with
`SUM(sales_price) FILTER (WHERE day_name = ...)`.

It also restricts `d_week_seq` to values associated with the selected
`d_month_seq` range, 1207 through 1230, before grouping by week and store.

### Rationale

The `FILTER` form expresses the day-specific aggregate directly and
is an alternative to conditional aggregation. The added week restriction
can reduce the rows that reach the grouping stage, provided the range
matches the weeks relevant to the intended query results.

### Results and validation

- Statement-timing median: 0.031 s original; 0.030 s optimized.
- Speedup: 1.033x; runtime reduction: 3.2%.
- Wall-clock median: 0.049257 s original; 0.048136 s optimized.
- Correctness: 100 rows matched exactly on SF1.

The performance difference is small and may be within measurement
variability. The optimization should not be presented as a substantial
speedup.

## 5. Q95 — Replace a sales self-join with grouped warehouse checks

### Changes

The original `ws_wh` CTE self-joins `web_sales` on order number and
finds orders associated with different warehouse keys. The optimized
version groups `web_sales` by order number and keeps groups where
`MIN(ws_warehouse_sk) <> MAX(ws_warehouse_sk)`.

The returns-order subquery is also simplified to select order numbers
directly from `web_returns`; the outer query still intersects those
orders with the orders selected by `ws_wh`.

### Rationale

A self-join can generate multiple row pairs for an order with sales
records in different warehouses. Grouping by order and comparing the
minimum and maximum warehouse keys can express the same different-
warehouse condition without generating those pairs. The simpler returns
subquery avoids an additional join to `ws_wh` that is redundant for the
outer order-membership condition.

### Results and validation

- Statement-timing median: 0.058 s original; 0.013 s optimized.
- Speedup: 4.462x; runtime reduction: 77.6%.
- Wall-clock median: 0.075556 s original; 0.028380 s optimized.
- Correctness: the single output row matched exactly on SF1.

Q95 had the largest measured improvement among these four queries.
The result is specific to this workload and environment.

## 6. Measurement method and limitations

Each version had one warm-up followed by five measured runs on SF1.
Warm-ups were excluded from the reported medians.

Two timing methods were recorded and are reported separately:

1. DuckDB CLI statement-level `real` timings. For multi-statement
   queries, statement timings were summed per run before calculating
   the median.
2. Separate wall-clock timings.

The two methods produce different absolute times and speedups, so their
results should not be mixed. DuckDB CLI timings are rounded; particularly
small differences should be interpreted cautiously.

The correctness comparisons were performed on the tested SF1 database.
They do not establish equivalence for every possible dataset or scale
factor. Q39's first statement is supported by a numeric-tolerance
comparison rather than exact multiset identity.

## 7. Supporting artifacts

- Original SQL: `queries/optimization/original/`
- Optimized SQL: `queries/optimization/optimized/`
- Existing timing and correctness notes: `reports/optimization/README.md`
- Statement timing results: `reports/optimization/statement_timing_summary.csv`
- Wall-clock results: `reports/optimization/wall_clock_summary.csv`
