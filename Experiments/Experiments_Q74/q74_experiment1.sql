-- Experimental setting: force the written join order
SET disabled_optimizers = 'join_order,build_side_probe_side';

EXPLAIN ANALYZE
WITH year_total AS (
    SELECT
        c.c_customer_id AS customer_id,
        c.c_first_name AS customer_first_name,
        c.c_last_name AS customer_last_name,
        d.d_year AS year,
        MAX(ss.ss_net_paid) AS year_total,
        's' AS sale_type
    FROM store_sales ss
    JOIN date_dim d
        ON ss.ss_sold_date_sk = d.d_date_sk
    JOIN customer c
        ON ss.ss_customer_sk = c.c_customer_sk
    WHERE d.d_year IN (2001, 2002)
    GROUP BY
        c.c_customer_id,
        c.c_first_name,
        c.c_last_name,
        d.d_year

    UNION ALL

    SELECT
        c.c_customer_id AS customer_id,
        c.c_first_name AS customer_first_name,
        c.c_last_name AS customer_last_name,
        d.d_year AS year,
        MAX(ws.ws_net_paid) AS year_total,
        'w' AS sale_type
    FROM web_sales ws
    JOIN date_dim d
        ON ws.ws_sold_date_sk = d.d_date_sk
    JOIN customer c
        ON ws.ws_bill_customer_sk = c.c_customer_sk
    WHERE d.d_year IN (2001, 2002)
    GROUP BY
        c.c_customer_id,
        c.c_first_name,
        c.c_last_name,
        d.d_year
)
SELECT
    t_s_secyear.customer_id,
    t_s_secyear.customer_first_name,
    t_s_secyear.customer_last_name
FROM year_total t_s_firstyear
JOIN year_total t_s_secyear
    ON t_s_firstyear.customer_id = t_s_secyear.customer_id
JOIN year_total t_w_firstyear
    ON t_s_firstyear.customer_id = t_w_firstyear.customer_id
JOIN year_total t_w_secyear
    ON t_s_firstyear.customer_id = t_w_secyear.customer_id
WHERE
    t_s_firstyear.sale_type = 's'
    AND t_s_secyear.sale_type = 's'
    AND t_w_firstyear.sale_type = 'w'
    AND t_w_secyear.sale_type = 'w'
    AND t_s_firstyear.year = 2001
    AND t_s_secyear.year = 2002
    AND t_w_firstyear.year = 2001
    AND t_w_secyear.year = 2002
    AND t_s_firstyear.year_total > 0
    AND t_w_firstyear.year_total > 0
    AND CASE
        WHEN t_w_firstyear.year_total > 0
        THEN t_w_secyear.year_total
             / t_w_firstyear.year_total
        ELSE NULL
    END >
    CASE
        WHEN t_s_firstyear.year_total > 0
        THEN t_s_secyear.year_total
             / t_s_firstyear.year_total
        ELSE NULL
    END
ORDER BY 2, 1, 3
LIMIT 100;

SET disabled_optimizers = '';