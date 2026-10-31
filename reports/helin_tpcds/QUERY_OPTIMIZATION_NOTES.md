# TPC-DS Query Optimization Notes

**Comparison engine:** DuckDB Python 1.5.6
**Datasets:** TPC-DS SF1, SF2, SF4, and SF8
**Queries:** Q23, Q39, Q59, Q95

## 1. Overview

The original SQL snapshots and source templates remain unchanged. The
optimized `.tpl` files in `query_templates_optimized/` are the source of
truth; the corresponding SF1 SQL snapshots are generated into
`queries/optimization/optimized/`. The reproducible generator combines
these overrides with the official templates for the other 95 queries.

The aim was to reduce unnecessary aggregation work, intermediate
grouping, and join work while retaining the query's intended results.
Performance and result equivalence were tested at four scales; this does
not prove equivalence for all datasets or generated query parameters.
None of the optimized templates or SQL snapshots contains an explicit
`MATERIALIZED` hint or creates a materialized table.

## 2. Q23 — Reuse customer-level aggregates

### Changes

The optimized template computes total store sales and sales in the
four-year period in one customer-level aggregate. A window maximum finds
the maximum period-specific customer sales; the qualifying customer CTE
then applies the threshold to total sales. This is an ordinary CTE, with
no explicit materialization directive.

The frequent-item grouping drops `substr(i_item_desc, 1, 30)`, retaining
the item key and date. The catalog and web sales rows are combined before
the item/customer membership predicates are applied; the second statement
groups by channel and customer name.

### Rationale

The rewrite consolidates customer calculations that the original performs
through separate aggregation paths. Removing the description expression
from the grouping key narrows the aggregate key, and applying membership
filters after the channel union may avoid repeating that logical filter
work. These are expected mechanisms, not measured plan statistics.

These benefits depend on DuckDB's execution plan and the data. The
runtime measurements show the result, but do not isolate the contribution
of each individual change.

### Results and validation

- At SF1/SF2/SF4/SF8, respectively: original medians were 0.061492,
  0.108043, 0.210513, and 0.491021 seconds; optimized medians were
  0.049405, 0.087126, 0.148325, and 0.304439 seconds.
- Speedups were 1.245x, 1.240x, 1.419x, and 1.613x, respectively.
- Both statements matched at every scale. The second statement returned
  0, 2, 0, and 2 rows at SF1, SF2, SF4, and SF8, respectively.

Agreement on these saved parameters and datasets is not proof of
equivalence for every dataset or parameter choice.

## 3. Q39 — Restrict inventory aggregation to relevant months

### Changes

The optimized `inv` CTE filters `d_moy` to the two requested months
before calculating the sample standard deviation and average inventory
quantity. It removes warehouse name from the intermediate selection and
grouping, retaining the warehouse key used downstream. Both statements
use the same restricted aggregate; the second retains its additional
`inv1.cov > 1.5` predicate.

### Rationale

Restricting inventory rows to the two months used by the final self-join
can reduce the number of rows entering the aggregate. Removing an unused
warehouse-name grouping attribute can also reduce intermediate grouping
width. The month is a template parameter, so the intended pair is not
limited to January and February.

### Results and validation

- At SF1/SF2/SF4/SF8, respectively: original medians were 0.024609,
  0.026124, 0.040675, and 0.079402 seconds; optimized medians were
  0.021064, 0.023758, 0.030481, and 0.057173 seconds.
- Speedups were 1.168x, 1.100x, 1.334x, and 1.389x, respectively.
- Both statements matched as duplicate-aware multisets at each scale:
  statement 1 returned 176, 226, 471, and 1,130 rows; statement 2 returned
  5, 6, 15, and 33 rows.
- Numeric values were compared with absolute and relative tolerances of
  1e-9; this is tolerance-equivalence, not bit-for-bit identity.

## 4. Q59 — Filtered aggregates and a narrower week range

### Changes

The optimized query replaces seven conditional expressions of the form
`SUM(CASE WHEN day_name = ... THEN sales_price ELSE NULL END)` with
`SUM(sales_price) FILTER (WHERE day_name = ...)`.

It also restricts `d_week_seq` to values associated with the selected
24-month `d_month_seq` range before grouping by week and store.

### Rationale

The `FILTER` form directly expresses each day-specific aggregate. The
week restriction excludes sales outside the two comparison periods before
grouping, which can reduce the rows reaching the aggregate.

### Results and validation

- At SF1/SF2/SF4/SF8, respectively: original medians were 0.030368,
  0.036718, 0.060722, and 0.089895 seconds; optimized medians were
  0.015459, 0.030474, 0.048957, and 0.066455 seconds.
- Speedups were 1.964x, 1.205x, 1.240x, and 1.353x, respectively.
- All 100 rows matched as duplicate-aware multisets at every scale.

The measured change is not uniform across scales and may be sensitive to
runtime variability. It should not be presented as a guaranteed speedup.

## 5. Q95 — Replace a sales self-join with grouped warehouse checks

### Changes

The original `ws_wh` CTE self-joins `web_sales` on order number and
finds orders associated with different warehouse keys. The optimized
version groups `web_sales` by order number and keeps groups where
`MIN(ws_warehouse_sk) <> MAX(ws_warehouse_sk)`.

The returns-order subquery selects order numbers directly from
`web_returns`; the outer query still intersects those orders with the
orders selected by `ws_wh`. The template retains the query's year, month,
and state parameters.

### Rationale

A self-join can generate multiple row pairs for an order with sales
records in different warehouses. Grouping by order and comparing the
minimum and maximum warehouse keys detects multiple non-null warehouse
values without generating those row pairs. Direct return-order
membership avoids joining `ws_wh` again inside the return subquery.

### Results and validation

- At SF1/SF2/SF4/SF8, respectively: original medians were 0.043171,
  0.051638, 0.088965, and 0.168389 seconds; optimized medians were
  0.006687, 0.009393, 0.013440, and 0.024095 seconds.
- Speedups were 6.456x, 5.498x, 6.619x, and 6.989x, respectively.
- The single output row matched at every scale.

Q95 had the largest measured improvement among these four queries.
The result is specific to this workload and environment.

## 6. Measurement method and limitations

`scripts/compare_and_time.py` uses DuckDB Python 1.5.6 in the selected
`.venv-benchmark` environment. It opens each SF database read-only, executes
all statements, and validates results before timing. Each version receives
one warm-up and five measured runs. Measurement order alternates by
repetition; medians are calculated from the five measured wall-clock
durations, including result fetching. There is one database connection per
query/scale pair.

Result comparison checks equal row counts and matches each row against one
unmatched row on the other side, so duplicate multiplicity is preserved.
Numeric comparisons use `math.isclose` with both absolute and relative
tolerances of 1e-9. All 16 query/scale rows in
`reports/optimization/four_queries_final.csv` have status `OK` and passed
validation. The saved CSV itself does not contain an engine-version field;
the comparison script now records that version in future output.

The optimizer rewrites are not accompanied by collected execution-plan
statistics. The measured timings therefore show end-to-end outcomes, not
which individual rewrite component caused them. Results apply only to the
saved SQL, data, settings, and runtime environment, and should not be mixed
with the separate baseline benchmark based on DuckDB CLI 1.4.3.

## 7. Supporting artifacts

- Original SQL: `queries/optimization/original/`
- Optimized SQL: `queries/optimization/optimized/`
- Optimized templates: `query_templates_optimized/`
- Combined workload generator: `scripts/generate_optimized_queries.sh`
- Comparison code and final CSV: `scripts/compare_and_time.py` and `reports/optimization/four_queries_final.csv`
