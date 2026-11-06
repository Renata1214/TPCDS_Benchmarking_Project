
with frequent_ss_items as
 (select i_item_sk item_sk
  from store_sales
      ,date_dim
      ,item
  where ss_sold_date_sk = d_date_sk
    and ss_item_sk = i_item_sk
    and d_year in (1999,1999+1,1999+2,1999+3)
  group by i_item_sk,d_date
  having count(*) >4),
 best_ss_customer as
 (select c_customer_sk
  from (select c_customer_sk, ssales, max(csales) over () tpcds_cmax
        from (select c_customer_sk,
                     sum(ss_quantity*ss_sales_price) ssales,
                     sum(case when d_year in (1999,1999+1,1999+2,1999+3)
                              then ss_quantity*ss_sales_price end) csales
              from store_sales
                   join customer on ss_customer_sk = c_customer_sk
                   left join date_dim on ss_sold_date_sk = d_date_sk
              group by c_customer_sk) per_customer) ranked
  where ssales > (95/100.0) * tpcds_cmax)
  select  sum(sales)
 from (select cs_quantity*cs_list_price sales
             ,cs_item_sk sold_item_sk
             ,cs_bill_customer_sk sold_cust_sk
       from catalog_sales
           ,date_dim
       where d_year = 1999
         and d_moy = 1
         and cs_sold_date_sk = d_date_sk
      union all
      select ws_quantity*ws_list_price
            ,ws_item_sk
            ,ws_bill_customer_sk
       from web_sales
           ,date_dim
       where d_year = 1999
         and d_moy = 1
         and ws_sold_date_sk = d_date_sk) all_sales
 where sold_item_sk in (select item_sk from frequent_ss_items)
   and sold_cust_sk in (select c_customer_sk from best_ss_customer)
 limit 100;
with frequent_ss_items as
 (select i_item_sk item_sk
  from store_sales
      ,date_dim
      ,item
  where ss_sold_date_sk = d_date_sk
    and ss_item_sk = i_item_sk
    and d_year in (1999,1999+1,1999+2,1999+3)
  group by i_item_sk,d_date
  having count(*) >4),
 best_ss_customer as
 (select c_customer_sk
  from (select c_customer_sk, ssales, max(csales) over () tpcds_cmax
        from (select c_customer_sk,
                     sum(ss_quantity*ss_sales_price) ssales,
                     sum(case when d_year in (1999,1999+1,1999+2,1999+3)
                              then ss_quantity*ss_sales_price end) csales
              from store_sales
                   join customer on ss_customer_sk = c_customer_sk
                   left join date_dim on ss_sold_date_sk = d_date_sk
              group by c_customer_sk) per_customer) ranked
  where ssales > (95/100.0) * tpcds_cmax)
  select  c_last_name,c_first_name,sales
 from (select c_last_name,c_first_name,sum(sales) sales
       from (select 1 channel
                   ,cs_bill_customer_sk sold_cust_sk
                   ,cs_item_sk sold_item_sk
                   ,cs_quantity*cs_list_price sales
             from catalog_sales
                 ,date_dim
             where d_year = 1999
               and d_moy = 1
               and cs_sold_date_sk = d_date_sk
            union all
            select 2
                  ,ws_bill_customer_sk
                  ,ws_item_sk
                  ,ws_quantity*ws_list_price
             from web_sales
                 ,date_dim
             where d_year = 1999
               and d_moy = 1
               and ws_sold_date_sk = d_date_sk) all_sales
           ,customer
       where sold_item_sk in (select item_sk from frequent_ss_items)
         and sold_cust_sk in (select c_customer_sk from best_ss_customer)
         and sold_cust_sk = c_customer_sk
       group by channel,c_last_name,c_first_name) by_channel
 order by c_last_name,c_first_name,sales
 limit 100;


