# TPC-DS Query Fixes — DuckDB Compatibility (SF=10)

These 99 SQL files are adapted from the official TPC-DS 4.0 templates to run on DuckDB.
Out of 99 queries, **20 required fixes**. The remaining 79 ran without modification.

---

## Fix 1 — ANSI date arithmetic syntax

**Affected queries:** Q5, Q12, Q16, Q20, Q21, Q32, Q37, Q40, Q50, Q62, Q77, Q80, Q82, Q92, Q94, Q95, Q98, Q99

**Error:**
```
Parser Error: syntax error at or near "days"
```

**Fix:**
```sql
-- BEFORE: cast('1998-08-04' as date) + 30 days
-- AFTER:  cast('1998-08-04' as date) + INTERVAL '30' DAY
```

---

## Fix 2 — Reserved keyword: `returns` (Q77)

**Error:** `Parser Error: syntax error at or near "returns"`

**Fix:** All column aliases named `returns` renamed to `total_returns`.

---

## Fix 3 — Reserved keyword: `at` (Q90)

**Error:** `Parser Error: syntax error at or near "at"`

**Fix:** Subquery alias `at` renamed to `am_count`.

---

## Fix 4 — Non-existent column: `c_last_review_date_sk` (Q30)

**Error:** `Binder Error: Referenced column "c_last_review_date_sk" not found`

**Fix:** Column removed from SELECT and ORDER BY.

---

## Benchmark Results (SF=10)

| Metric | Value |
|--------|-------|
| Working | 99/99 |
| Failed | 0 (none) |
| Total time | 50.40s |
| Slowest query | Q22 (21.936s) |
