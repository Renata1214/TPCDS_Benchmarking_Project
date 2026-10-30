
with v1 as (
     select i_category,
            i_brand,
            s_store_name,
            s_company_name,
            d_year,
            d_moy,
            sum(ss_sales_price) as sum_sales,
            avg(sum(ss_sales_price)) over (
                partition by i_category, i_brand,
                             s_store_name, s_company_name, d_year
            ) as avg_monthly_sales
     from item, store_sales, date_dim, store
     where ss_item_sk = i_item_sk
       and ss_sold_date_sk = d_date_sk
       and ss_store_sk = s_store_sk
       and (
           d_year = 2000
           or (d_year = 2000-1 and d_moy = 12)
           or (d_year = 2000+1 and d_moy = 1)
       )
     group by i_category, i_brand,
              s_store_name, s_company_name,
              d_year, d_moy
 ),
 v2 as (
     select i_category, i_brand
            ,d_year, d_moy
            ,v1.avg_monthly_sales
            ,v1.sum_sales
            ,v1.i_category as __i_category
            ,v1.i_brand as __i_brand
            ,v1.s_store_name as __s_store_name
            ,v1.s_company_name as __s_company_name
            ,lag(v1.sum_sales) over (
                partition by v1.i_category, v1.i_brand,
                             v1.s_store_name, v1.s_company_name
                order by v1.d_year, v1.d_moy
            ) as psum
            ,lead(v1.sum_sales) over (
                partition by v1.i_category, v1.i_brand,
                             v1.s_store_name, v1.s_company_name
                order by v1.d_year, v1.d_moy
            ) as nsum
            ,lag(1) over (
                partition by v1.i_category, v1.i_brand,
                             v1.s_store_name, v1.s_company_name
                order by v1.d_year, v1.d_moy
            ) as has_previous
            ,lead(1) over (
                partition by v1.i_category, v1.i_brand,
                             v1.s_store_name, v1.s_company_name
                order by v1.d_year, v1.d_moy
            ) as has_next
     from v1
 )
  select

        i_category, i_brand
        ,d_year, d_moy
        ,avg_monthly_sales
        ,sum_sales
        ,psum
        ,nsum
 from v2
 where d_year = 2000
   and avg_monthly_sales > 0
   and __i_category is not null
   and __i_brand is not null
   and __s_store_name is not null
   and __s_company_name is not null
   and has_previous is not null
   and has_next is not null
   and case
       when avg_monthly_sales > 0
       then abs(sum_sales - avg_monthly_sales) / avg_monthly_sales
       else null
   end > 0.1
 order by sum_sales - avg_monthly_sales, nsum
 limit 100;


