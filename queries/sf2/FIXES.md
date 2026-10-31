# TPC-DS Query Fixes — DuckDB Compatibility (SF=2)

These 99 SQL files are adapted from the official TPC-DS 4.0 templates to run on DuckDB.
Out of 99 queries, **20 required fixes**. The remaining 79 ran without modification.

---

## Fix 1 — ANSI date arithmetic syntax

**Affected queries:** Q5, Q12, Q16, Q20, Q21, Q32, Q37, Q40, Q50, Q62, Q77, Q80, Q82, Q92, Q94, Q95, Q98, Q99

**Error:**
```
Parser Error: syntax error at or near "days"
```

**Root cause:**  
The official TPC-DS templates use ANSI SQL date arithmetic (`+ 30 days`), which DuckDB does not support.

**Fix:**
```sql
-- BEFORE (ANSI SQL):
and d_date between cast('1998-08-04' as date)
           and (cast('1998-08-04' as date) + 30 days)

-- AFTER (DuckDB):
and d_date between cast('1998-08-04' as date)
           and (cast('1998-08-04' as date) + INTERVAL '30' DAY)
```

---

## Fix 2 — Reserved keyword: `returns`

**Affected query:** Q77

**Error:**
```
Parser Error: syntax error at or near "returns"
```

**Root cause:**  
`returns` is a reserved keyword in DuckDB and cannot be used as a column alias.

**Fix:**  
All occurrences of the alias `returns` were renamed to `total_returns` in both the CTE definitions and the outer SELECT.

```sql
-- BEFORE:
sum(sr_return_amt) as returns

-- AFTER:
sum(sr_return_amt) as total_returns
```

---

## Fix 3 — Reserved keyword: `at`

**Affected query:** Q90

**Error:**
```
Parser Error: syntax error at or near "at"
```

**Root cause:**  
`at` is a reserved keyword in DuckDB and cannot be used as a subquery alias.

**Fix:**  
The subquery alias `at` was renamed to `am_count`.

```sql
-- BEFORE:
( select count(*) amc from web_sales, ... ) at,

-- AFTER:
( select count(*) amc from web_sales, ... ) am_count,
```

---

## Fix 4 — Non-existent column: `c_last_review_date_sk`

**Affected query:** Q30

**Error:**
```
Binder Error: Referenced column "c_last_review_date_sk" not found in FROM clause
```

**Root cause:**  
The column `c_last_review_date_sk` is referenced in the SELECT and ORDER BY clauses but does not exist in the DuckDB TPC-DS `customer` table schema.

**Fix:**  
The column was removed from both the SELECT list and the ORDER BY clause.

```sql
-- BEFORE:
select c_customer_id, ..., c_last_review_date_sk, ctr_total_return
...
order by c_customer_id, ..., c_last_review_date_sk, ctr_total_return

-- AFTER:
select c_customer_id, ..., ctr_total_return
...
order by c_customer_id, ..., ctr_total_return
```

---

## Summary

| Fix | Queries affected | Count |
|-----|-----------------|-------|
| ANSI `X days` → `INTERVAL 'X' DAY` | Q5, Q12, Q16, Q20, Q21, Q32, Q37, Q40, Q50, Q62, Q77, Q80, Q82, Q92, Q94, Q95, Q98, Q99 | 18 |
| `returns` → `total_returns` | Q77 | 1 |
| `at` → `am_count` | Q90 | 1 |
| Remove `c_last_review_date_sk` | Q30 | 1 |
| **Total fixed** | | **20** |
| No change needed | | 79 |
