# DuckDB optimizations for TPC-DS Q8, Q11, Q64 and Q67

These changes preserve the query templates' parameters and rewrite how DuckDB computes their results. The four updated templates are in `Kit/DSGen-software-code-4.0.0/query_templates/`. This directory contains the original SQL, the tested optimized SQL for SF1/2/4/8, validation scripts and local measurements.

## Results and measurement conditions

Speedup is median original execution time divided by median optimized execution time. A value above 1 means the optimized query was faster.

| Query | SF1 | SF2 | SF4 | SF8 |
|---|---:|---:|---:|---:|
| Q8 | 7.41x | 7.77x | 7.33x | 4.69x |
| Q11 | 2.46x | 2.44x | 2.38x | 2.18x |
| Q64 | 1.06x | 1.06x | 1.37x | 1.24x |
| Q67 | 1.34x | 1.38x | 1.62x | 2.36x |

The tests used the DuckDB **1.4.3 Python package**, four execution threads and a 4 GB DuckDB memory limit on the same local macOS machine and databases. Each original/optimized pair received one warm-up execution and four measured repetitions, alternating execution order. Warm-ups were excluded from the medians. Q8/Q11/Q64 were measured on 27 October 2026; the final Q67 rewrite was measured separately on 28 October 2026 using the same settings. Raw timings are in `measurements.json`; `q67_retry_measurements.json` also records the final Q67 experiment.

These are short, local, query-level experiments, not an official TPC-DS result or a complete 99-query workload benchmark. In particular, warm-up here means one execution of each variant, not the repository's full-workload warm-up protocol. Do not calculate speedups by comparing these macOS timings with the earlier Linux timings. The small Q64 gains at SF1/SF2 require caution when interpreting measurement variation.

## Q8: represent the ZIP list as a relation

### Original computation

The query selects ZIP codes from a long literal `IN` list, intersects them with ZIP codes satisfying the preferred-customer count condition, and uses their two-character prefixes to match stores. It sums net profit for the selected year and quarter.

### Change

The 400 ZIP parameters are represented as a materialized CTE built with `VALUES`:

```sql
WITH zip_list AS MATERIALIZED (
    SELECT *
    FROM (VALUES ('[ZIP.1]'), ('[ZIP.2]') /* remaining ZIP parameters */) AS z(zip)
)
```

The address filter then uses:

```sql
WHERE substr(ca_zip, 1, 5) IN (SELECT zip FROM zip_list)
```

This is a relational membership test rather than the original long literal expression. On the tested DuckDB version and data, this representation produced a substantially faster execution. This does not imply that every literal `IN` list is slow in every SQL engine.

The existing `INTERSECT`, preferred-customer `HAVING count(*) > 10`, date filters, store-prefix join and final profit aggregation are unchanged. `HAVING` was not added as an optimization. ZIP membership remains a membership test, so duplicates in the list cannot multiply address rows. The later store-prefix join's existing multiplicity is preserved.

SF1/SF2/SF4 return no rows even in the original query; SF8 returns three rows. Empty-result matches alone are weak evidence, so the nonempty SF8 comparison is relevant.

## Q11: aggregate sales before joining customer attributes

### Original computation

The query computes annual store and web amounts grouped by customer attributes, then references those totals four times: store first/second year and web first/second year. It returns customers whose web second-year/first-year ratio exceeds the corresponding store ratio, with positive first-year totals.

Joining sales to customer names and other text attributes before aggregation exposes a large number of sales rows to the wider grouping keys.

### Change

Each sales channel is first aggregated by its customer surrogate key and year, limited to the two required years:

```sql
SELECT ss_customer_sk, d_year,
       SUM(ss_ext_list_price - ss_ext_discount_amt) AS net_amount
FROM store_sales
JOIN date_dim ON ss_sold_date_sk = d_date_sk
WHERE d_year IN ([YEAR], [YEAR] + 1)
GROUP BY ss_customer_sk, d_year
```

The equivalent rewrite is applied to `web_sales` using `ws_bill_customer_sk`. Customer attributes are joined after this reduction. The original outer grouping by customer attributes is retained and sums `net_amount`.

The main benefit is reducing the rows reaching the customer-attribute join and wide aggregation. Early year restriction also makes the required range explicit; DuckDB may already push some original predicates down, so the gain should not be attributed solely to the new year filter.

The store/web `UNION ALL`, four references, ratio calculations, positive-total conditions, output selection, ordering and limit are unchanged. Template parameters such as `[YEAR]` and `[SELECTONE]` remain available.

## Q64: restrict product and year eligibility earlier

### Original computation

The `cs_ui` CTE joins catalog sales and returns by item and order number, aggregates by item, and keeps items satisfying:

```sql
HAVING SUM(cs_ext_list_price) >
       2 * SUM(cr_refunded_cash + cr_reversed_charge + cr_store_credit)
```

The later `cross_sales` CTE joins store sales/returns and customer, item, address and demographic dimensions. Its result is self-joined to compare consecutive sales years.

### Changes

1. Add an item-membership filter inside `cs_ui` using the same color and price conditions already required downstream.
2. Restrict `cross_sales` to `d1.d_year IN ([YEAR], [YEAR] + 1)` before its grouping.

This avoids processing catalog groups for products that cannot reach the final result and avoids building cross-sales groups for irrelevant sales years. Product eligibility is expressed as `IN (SELECT i_item_sk ...)`, avoiding an additional multiplicity-producing product join.

The `HAVING` expression already existed and is unchanged. Filtering out an entire ineligible item does not alter another item's aggregate. All original sale/return joins and their multiplicity remain. Both original price intervals are retained; `BETWEEN` includes its endpoints. Only the sales-date year (`d1`) is restricted, not the customer's other date dimensions (`d2` and `d3`). The final count comparison, self-join keys, output and ordering remain unchanged.

## Q67: compute the ROLLUP hierarchy incrementally

### Original computation

The query computes sales with `SUM(COALESCE(ss_sales_price * ss_quantity, 0))`, groups using an eight-column `ROLLUP`, then applies `RANK()` within each category. Eight grouping columns produce nine grouping levels, including the grand total. Earlier saved SF8 profiles showed approximately 4.53 million aggregate rows, making aggregation and the subsequent window operation important costs.

### Change

Replace the `ROLLUP` expression with materialized aggregation stages:

- `g8`: all eight original grouping columns.
- `g7`: remove store from the grouping and sum `g8` totals.
- `g6`: remove month and sum `g7` totals.
- Continue through `g1`, which groups by category.
- `g0`: the grand total.

Each stage aggregates the preceding stage rather than expressing all levels in one `ROLLUP`. A `UNION ALL` combines the nine levels, padding rolled-up columns with `NULL` to reproduce the original output structure. Materialization makes the intermediate stages explicit and available for reuse. It does not mean a permanent table is created or that every intermediate must fit in RAM.

The rewrite was faster at all four tested scales. This is an observed result for the tested workload, not a claim that `ROLLUP` necessarily rescans the input nine times or that incremental aggregation is universally faster.

`UNION ALL` is essential: ordinary `UNION` could remove duplicate-looking rows from different grouping levels, particularly with real NULL dimension values. The original `RANK() OVER (PARTITION BY i_category ORDER BY sumsales DESC)` is preserved over the combined detail/subtotal result. It is not replaced by `ROW_NUMBER()`, which treats ties differently. Neither `rk <= 100` nor the final `LIMIT 100` is moved before aggregation/ranking.

An earlier monthly-preaggregation candidate regressed on smaller scales and is not the Q67 implementation included here.

## Correctness checks

- All four queries were compared at SF1, SF2, SF4 and SF8.
- The limited outputs matched. Full outputs were also compared after removing the final `LIMIT 100`, using row multisets (including duplicate counts) and output types.
- The final Q67 additionally matched at four alternate month-sequence starts on SF1.
- Q67 also matched on three small synthetic cases: empty input; NULLs and tied values; duplicate dimension rows.
- Template substitution checks confirmed that the four templates, expanded with the existing per-scale parameter values, match the tested optimized SQL after whitespace normalization.

These checks support equivalence for the tested data and parameters. They are not an exhaustive proof for all possible inputs. The template substitution checks do not invoke `dsqgen`; real regeneration with the team's Linux/Docker generator still needs verification. The Q67 extra checks are recorded in `q67_full_checks.json` and `q67_edge_checks.json`; the standalone scripts below rerun the four-scale comparisons.

## Files and reproduction

- `baseline/sfN/`: original SQL snapshots, taken before modification.
- `baseline/templates/`: original template snapshots.
- `sql/sfN/`: optimized SQL for the existing scale-specific parameters.
- `templates/`: snapshots of the four updated canonical templates.
- `measurements.json`, `comparison.csv`: recorded local timings.
- `full_result_checks.json`, `template_checks.json`: validation records.

**Do not compare against the current generated SQL in the author's working checkout as an original baseline: those files have already been updated. Use `baseline/`.** The repository normally ignores `queries/sf*/`; the explicit snapshots here make the tested SQL reviewable without changing that policy. Large raw datasets, database files and unrelated experiments are not included.

From the repository root, with the existing `duckdb/tpcds_sfN.duckdb` databases available:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r optimizations/q8_q11_q64_q67/requirements.txt
python optimizations/q8_q11_q64_q67/check_templates.py
python optimizations/q8_q11_q64_q67/check_full_results.py
python optimizations/q8_q11_q64_q67/validate.py --repo "$PWD"
```

The scripts open the databases read-only. DuckDB may create temporary spill files in the experiment directory. The last two scripts require the actual databases; they do not generate data. Running them overwrites the corresponding saved validation/measurement files, so preserve published evidence before repeating a run.

After regenerating SQL with `dsqgen` in the team's pinned Linux/Docker environment, repeat correctness checks and run the complete benchmark using the same hardware, settings, query order, full-workload warm-up and repeat count for both variants. Docker execution and authenticated GitHub synchronization were not established by the earlier local SQL tests.
