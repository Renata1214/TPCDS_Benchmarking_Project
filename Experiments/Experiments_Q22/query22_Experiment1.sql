WITH item_inventory AS (
    SELECT
        inv_item_sk,
        SUM(inv_quantity_on_hand) AS quantity_sum,
        COUNT(inv_quantity_on_hand) AS quantity_count
    FROM inventory
    JOIN date_dim
        ON inv_date_sk = d_date_sk
    WHERE d_month_seq BETWEEN 1212 AND 1223
    GROUP BY inv_item_sk
)
SELECT
    i_product_name,
    i_brand,
    i_class,
    i_category,
    SUM(quantity_sum)
        / NULLIF(SUM(quantity_count), 0) AS qoh
FROM item_inventory
JOIN item
    ON inv_item_sk = i_item_sk
GROUP BY ROLLUP(
    i_product_name,
    i_brand,
    i_class,
    i_category
)
ORDER BY
    qoh,
    i_product_name,
    i_brand,
    i_class,
    i_category
LIMIT 100;