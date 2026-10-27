
with g8 as materialized (select i_category
                  ,i_class
                  ,i_brand
                  ,i_product_name
                  ,d_year
                  ,d_qoy
                  ,d_moy
                  ,s_store_id
                  ,sum(coalesce(ss_sales_price*ss_quantity,0)) sumsales
            from store_sales
                ,date_dim
                ,store
                ,item
       where  ss_sold_date_sk=d_date_sk
          and ss_item_sk=i_item_sk
          and ss_store_sk = s_store_sk
          and d_month_seq between 1212 and 1212+11
       group by i_category, i_class, i_brand, i_product_name, d_year, d_qoy, d_moy,s_store_id),
g7 as materialized (select i_category, i_class, i_brand, i_product_name, d_year, d_qoy, d_moy, sum(sumsales) sumsales from g8 group by i_category, i_class, i_brand, i_product_name, d_year, d_qoy, d_moy),
g6 as materialized (select i_category, i_class, i_brand, i_product_name, d_year, d_qoy, sum(sumsales) sumsales from g7 group by i_category, i_class, i_brand, i_product_name, d_year, d_qoy),
g5 as materialized (select i_category, i_class, i_brand, i_product_name, d_year, sum(sumsales) sumsales from g6 group by i_category, i_class, i_brand, i_product_name, d_year),
g4 as materialized (select i_category, i_class, i_brand, i_product_name, sum(sumsales) sumsales from g5 group by i_category, i_class, i_brand, i_product_name),
g3 as materialized (select i_category, i_class, i_brand, sum(sumsales) sumsales from g4 group by i_category, i_class, i_brand),
g2 as materialized (select i_category, i_class, sum(sumsales) sumsales from g3 group by i_category, i_class),
g1 as materialized (select i_category, sum(sumsales) sumsales from g2 group by i_category),
g0 as materialized (select sum(sumsales) sumsales from g1),
rollup_results as (select i_category, i_class, i_brand, i_product_name, d_year, d_qoy, d_moy, s_store_id, sumsales from g8
union all
select i_category, i_class, i_brand, i_product_name, d_year, d_qoy, d_moy, NULL as s_store_id, sumsales from g7
union all
select i_category, i_class, i_brand, i_product_name, d_year, d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g6
union all
select i_category, i_class, i_brand, i_product_name, d_year, NULL as d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g5
union all
select i_category, i_class, i_brand, i_product_name, NULL as d_year, NULL as d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g4
union all
select i_category, i_class, i_brand, NULL as i_product_name, NULL as d_year, NULL as d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g3
union all
select i_category, i_class, NULL as i_brand, NULL as i_product_name, NULL as d_year, NULL as d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g2
union all
select i_category, NULL as i_class, NULL as i_brand, NULL as i_product_name, NULL as d_year, NULL as d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g1
union all
select NULL as i_category, NULL as i_class, NULL as i_brand, NULL as i_product_name, NULL as d_year, NULL as d_qoy, NULL as d_moy, NULL as s_store_id, sumsales from g0)
select  *
from (select i_category
            ,i_class
            ,i_brand
            ,i_product_name
            ,d_year
            ,d_qoy
            ,d_moy
            ,s_store_id
            ,sumsales
            ,rank() over (partition by i_category order by sumsales desc) rk
      from (select * from rollup_results)dw1) dw2
where rk <= 100
order by i_category
        ,i_class
        ,i_brand
        ,i_product_name
        ,d_year
        ,d_qoy
        ,d_moy
        ,s_store_id
        ,sumsales
        ,rk
limit 100;


