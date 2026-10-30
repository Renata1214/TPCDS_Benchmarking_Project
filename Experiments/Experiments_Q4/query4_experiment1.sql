
WITH sales_by_key AS NOT MATERIALIZED (
    SELECT
        ss.ss_customer_sk AS customer_sk,
        d.d_year AS dyear,
        's' AS sale_type,
        SUM(
            ((ss.ss_ext_list_price
            - ss.ss_ext_wholesale_cost
            - ss.ss_ext_discount_amt)
            + ss.ss_ext_sales_price) / 2
        ) AS year_total
    FROM store_sales ss
    JOIN date_dim d
        ON ss.ss_sold_date_sk = d.d_date_sk
    WHERE d.d_year IN (2001, 2002)
    GROUP BY ss.ss_customer_sk, d.d_year

    UNION ALL

    SELECT
        cs.cs_bill_customer_sk AS customer_sk,
        d.d_year AS dyear,
        'c' AS sale_type,
        SUM(
            ((cs.cs_ext_list_price
            - cs.cs_ext_wholesale_cost
            - cs.cs_ext_discount_amt)
            + cs.cs_ext_sales_price) / 2
        ) AS year_total
    FROM catalog_sales cs
    JOIN date_dim d
        ON cs.cs_sold_date_sk = d.d_date_sk
    WHERE d.d_year IN (2001, 2002)
    GROUP BY cs.cs_bill_customer_sk, d.d_year

    UNION ALL

    SELECT
        ws.ws_bill_customer_sk AS customer_sk,
        d.d_year AS dyear,
        'w' AS sale_type,
        SUM(
            ((ws.ws_ext_list_price
            - ws.ws_ext_wholesale_cost
            - ws.ws_ext_discount_amt)
            + ws.ws_ext_sales_price) / 2
        ) AS year_total
    FROM web_sales ws
    JOIN date_dim d
        ON ws.ws_sold_date_sk = d.d_date_sk
    WHERE d.d_year IN (2001, 2002)
    GROUP BY ws.ws_bill_customer_sk, d.d_year
),

year_total AS NOT MATERIALIZED (
    SELECT
        c.c_customer_id AS customer_id,
        c.c_first_name AS customer_first_name,
        c.c_last_name AS customer_last_name,
        c.c_preferred_cust_flag AS customer_preferred_cust_flag,
        c.c_birth_country AS customer_birth_country,
        c.c_login AS customer_login,
        c.c_email_address AS customer_email_address,
        s.dyear,
        s.sale_type,
        SUM(s.year_total) AS year_total
    FROM sales_by_key s
    JOIN customer c
        ON s.customer_sk = c.c_customer_sk
    GROUP BY
        c.c_customer_id,
        c.c_first_name,
        c.c_last_name,
        c.c_preferred_cust_flag,
        c.c_birth_country,
        c.c_login,
        c.c_email_address,
        s.dyear,
        s.sale_type
)

SELECT
    s02.customer_id,
    s02.customer_first_name,
    s02.customer_last_name,
    s02.customer_email_address
FROM year_total s01
JOIN year_total s02
    ON s01.customer_id = s02.customer_id
   AND s02.sale_type = 's'
   AND s02.dyear = 2002
JOIN year_total c01
    ON s01.customer_id = c01.customer_id
   AND c01.sale_type = 'c'
   AND c01.dyear = 2001
JOIN year_total c02
    ON s01.customer_id = c02.customer_id
   AND c02.sale_type = 'c'
   AND c02.dyear = 2002
JOIN year_total w01
    ON s01.customer_id = w01.customer_id
   AND w01.sale_type = 'w'
   AND w01.dyear = 2001
JOIN year_total w02
    ON s01.customer_id = w02.customer_id
   AND w02.sale_type = 'w'
   AND w02.dyear = 2002
WHERE s01.sale_type = 's'
  AND s01.dyear = 2001
  AND s01.year_total > 0
  AND c01.year_total > 0
  AND w01.year_total > 0
  AND CASE WHEN c01.year_total > 0
           THEN c02.year_total / c01.year_total
           ELSE NULL END
      > CASE WHEN s01.year_total > 0
             THEN s02.year_total / s01.year_total
             ELSE NULL END
  AND CASE WHEN c01.year_total > 0
           THEN c02.year_total / c01.year_total
           ELSE NULL END
      > CASE WHEN w01.year_total > 0
             THEN w02.year_total / w01.year_total
             ELSE NULL END
ORDER BY
    s02.customer_id,
    s02.customer_first_name,
    s02.customer_last_name,
    s02.customer_email_address
LIMIT 100;
