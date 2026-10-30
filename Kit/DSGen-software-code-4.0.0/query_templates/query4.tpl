--
-- Legal Notice 
-- 
-- This document and associated source code (the "Work") is a part of a 
-- benchmark specification maintained by the TPC. 
-- 
-- The TPC reserves all right, title, and interest to the Work as provided 
-- under U.S. and international laws, including without limitation all patent 
-- and trademark rights therein. 
-- 
-- No Warranty 
-- 
-- 1.1 TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE INFORMATION 
--     CONTAINED HEREIN IS PROVIDED "AS IS" AND WITH ALL FAULTS, AND THE 
--     AUTHORS AND DEVELOPERS OF THE WORK HEREBY DISCLAIM ALL OTHER 
--     WARRANTIES AND CONDITIONS, EITHER EXPRESS, IMPLIED OR STATUTORY, 
--     INCLUDING, BUT NOT LIMITED TO, ANY (IF ANY) IMPLIED WARRANTIES, 
--     DUTIES OR CONDITIONS OF MERCHANTABILITY, OF FITNESS FOR A PARTICULAR 
--     PURPOSE, OF ACCURACY OR COMPLETENESS OF RESPONSES, OF RESULTS, OF 
--     WORKMANLIKE EFFORT, OF LACK OF VIRUSES, AND OF LACK OF NEGLIGENCE. 
--     ALSO, THERE IS NO WARRANTY OR CONDITION OF TITLE, QUIET ENJOYMENT, 
--     QUIET POSSESSION, CORRESPONDENCE TO DESCRIPTION OR NON-INFRINGEMENT 
--     WITH REGARD TO THE WORK. 
-- 1.2 IN NO EVENT WILL ANY AUTHOR OR DEVELOPER OF THE WORK BE LIABLE TO 
--     ANY OTHER PARTY FOR ANY DAMAGES, INCLUDING BUT NOT LIMITED TO THE 
--     COST OF PROCURING SUBSTITUTE GOODS OR SERVICES, LOST PROFITS, LOSS 
--     OF USE, LOSS OF DATA, OR ANY INCIDENTAL, CONSEQUENTIAL, DIRECT, 
--     INDIRECT, OR SPECIAL DAMAGES WHETHER UNDER CONTRACT, TORT, WARRANTY,
--     OR OTHERWISE, ARISING IN ANY WAY OUT OF THIS OR ANY OTHER AGREEMENT 
--     RELATING TO THE WORK, WHETHER OR NOT SUCH AUTHOR OR DEVELOPER HAD 
--     ADVANCE NOTICE OF THE POSSIBILITY OF SUCH DAMAGES. 
-- 
-- Contributors:
-- 
define YEAR=random(1998,2001,uniform);
define SELECTONE= text({"s02.customer_preferred_cust_flag",1}
                       ,{"s02.customer_birth_country",1}
                       ,{"s02.customer_login",1}
                       ,{"s02.customer_email_address",1});
define _LIMIT=100;

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
    WHERE d.d_year IN ([YEAR], [YEAR] + 1)
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
    WHERE d.d_year IN ([YEAR], [YEAR] + 1)
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
    WHERE d.d_year IN ([YEAR], [YEAR] + 1)
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

[_LIMITA]
SELECT
[_LIMITB]
    s02.customer_id,
    s02.customer_first_name,
    s02.customer_last_name,
    [SELECTONE]
FROM year_total s01
JOIN year_total s02
    ON s01.customer_id = s02.customer_id
   AND s02.sale_type = 's'
   AND s02.dyear = [YEAR] + 1
JOIN year_total c01
    ON s01.customer_id = c01.customer_id
   AND c01.sale_type = 'c'
   AND c01.dyear = [YEAR]
JOIN year_total c02
    ON s01.customer_id = c02.customer_id
   AND c02.sale_type = 'c'
   AND c02.dyear = [YEAR] + 1
JOIN year_total w01
    ON s01.customer_id = w01.customer_id
   AND w01.sale_type = 'w'
   AND w01.dyear = [YEAR]
JOIN year_total w02
    ON s01.customer_id = w02.customer_id
   AND w02.sale_type = 'w'
   AND w02.dyear = [YEAR] + 1
WHERE s01.sale_type = 's'
  AND s01.dyear = [YEAR]
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
    [SELECTONE]
[_LIMITC];
