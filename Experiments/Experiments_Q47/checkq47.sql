CREATE TEMP TABLE baseline_result AS
-- Paste original Query 47 here, without its final semicolon

with v1 as(
 select i_category, i_brand,
        s_store_name, s_company_name,
        d_year, d_moy,
        sum(ss_sales_price) sum_sales,
        avg(sum(ss_sales_price)) over
          (partition by i_category, i_brand,
                     s_store_name, s_company_name, d_year)
          avg_monthly_sales,
        rank() over
          (partition by i_category, i_brand,
                     s_store_name, s_company_name
           order by d_year, d_moy) rn
 from item, store_sales, date_dim, store
 where ss_item_sk = i_item_sk and
       ss_sold_date_sk = d_date_sk and
       ss_store_sk = s_store_sk and
       (
         d_year = 2000 or
         ( d_year = 2000-1 and d_moy =12) or
         ( d_year = 2000+1 and d_moy =1)
       )
 group by i_category, i_brand,
          s_store_name, s_company_name,
          d_year, d_moy),
 v2 as(
 select v1.i_category, v1.i_brand
        ,v1.d_year, v1.d_moy
        ,v1.avg_monthly_sales
        ,v1.sum_sales, v1_lag.sum_sales psum, v1_lead.sum_sales nsum
 from v1, v1 v1_lag, v1 v1_lead
 where v1.i_category = v1_lag.i_category and
       v1.i_category = v1_lead.i_category and
       v1.i_brand = v1_lag.i_brand and
       v1.i_brand = v1_lead.i_brand and
       v1.s_store_name = v1_lag.s_store_name and
       v1.s_store_name = v1_lead.s_store_name and
       v1.s_company_name = v1_lag.s_company_name and
       v1.s_company_name = v1_lead.s_company_name and
       v1.rn = v1_lag.rn + 1 and
       v1.rn = v1_lead.rn - 1)
  select  *
 from v2
 where  d_year = 2000 and    
        avg_monthly_sales > 0 and
        case when avg_monthly_sales > 0 then abs(sum_sales - avg_monthly_sales) / avg_monthly_sales else null end > 0.1
 order by sum_sales - avg_monthly_sales, nsum
 limit 100;

;

CREATE TEMP TABLE optimized_result AS
-- Paste rewritten Query 47 here, without its final semicolon

WITH v1 AS (
    SELECT
        i_category,
        i_brand,
        s_store_name,
        s_company_name,
        d_year,
        d_moy,

        SUM(ss_sales_price) AS sum_sales,

        AVG(SUM(ss_sales_price)) OVER (
            PARTITION BY
                i_category,
                i_brand,
                s_store_name,
                s_company_name,
                d_year
        ) AS avg_monthly_sales

    FROM item, store_sales, date_dim, store

    WHERE ss_item_sk = i_item_sk
      AND ss_sold_date_sk = d_date_sk
      AND ss_store_sk = s_store_sk
      AND (
          d_year = 2000
          OR (d_year = 1999 AND d_moy = 12)
          OR (d_year = 2001 AND d_moy = 1)
      )

    GROUP BY
        i_category,
        i_brand,
        s_store_name,
        s_company_name,
        d_year,
        d_moy
),

v2 AS (
    SELECT
        i_category,
        i_brand,
        s_store_name,
        s_company_name,
        d_year,
        d_moy,
        avg_monthly_sales,
        sum_sales,

        LAG(sum_sales) OVER (
            PARTITION BY
                i_category,
                i_brand,
                s_store_name,
                s_company_name
            ORDER BY d_year, d_moy
        ) AS psum,

        LEAD(sum_sales) OVER (
            PARTITION BY
                i_category,
                i_brand,
                s_store_name,
                s_company_name
            ORDER BY d_year, d_moy
        ) AS nsum,

        -- Detect whether adjacent rows exist.
        -- Do not use psum/nsum IS NOT NULL:
        -- SUM may legitimately be NULL.
        LAG(1) OVER (
            PARTITION BY
                i_category,
                i_brand,
                s_store_name,
                s_company_name
            ORDER BY d_year, d_moy
        ) AS has_previous,

        LEAD(1) OVER (
            PARTITION BY
                i_category,
                i_brand,
                s_store_name,
                s_company_name
            ORDER BY d_year, d_moy
        ) AS has_next

    FROM v1
)

SELECT
    i_category,
    i_brand,
    d_year,
    d_moy,
    avg_monthly_sales,
    sum_sales,
    psum,
    nsum

FROM v2

WHERE d_year = 2000
  AND avg_monthly_sales > 0

  -- Preserve the original INNER JOIN semantics
  -- for nullable grouping attributes.
  AND i_category IS NOT NULL
  AND i_brand IS NOT NULL
  AND s_store_name IS NOT NULL
  AND s_company_name IS NOT NULL

  -- Original self-joins require both neighbors.
  AND has_previous IS NOT NULL
  AND has_next IS NOT NULL

  AND CASE
      WHEN avg_monthly_sales > 0
      THEN ABS(sum_sales - avg_monthly_sales)
           / avg_monthly_sales
      ELSE NULL
  END > 0.1

ORDER BY
    sum_sales - avg_monthly_sales,
    nsum

LIMIT 100;

;

