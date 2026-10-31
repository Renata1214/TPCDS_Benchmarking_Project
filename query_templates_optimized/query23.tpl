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
 define YEAR= random(1998, 2000, uniform);
 define MONTH = random(1,7,uniform);
 define TOPPERCENT=random(95,95,uniform);
 define _LIMIT=100;

 with frequent_ss_items as
 (select i_item_sk item_sk
  from store_sales
      ,date_dim
      ,item
  where ss_sold_date_sk = d_date_sk
    and ss_item_sk = i_item_sk
    and d_year in ([YEAR],[YEAR]+1,[YEAR]+2,[YEAR]+3)
  group by i_item_sk,d_date
  having count(*) >4),
 best_ss_customer as
 (select c_customer_sk
  from (select c_customer_sk, ssales, max(csales) over () tpcds_cmax
        from (select c_customer_sk,
                     sum(ss_quantity*ss_sales_price) ssales,
                     sum(case when d_year in ([YEAR],[YEAR]+1,[YEAR]+2,[YEAR]+3)
                              then ss_quantity*ss_sales_price end) csales
              from store_sales
                   join customer on ss_customer_sk = c_customer_sk
                   left join date_dim on ss_sold_date_sk = d_date_sk
              group by c_customer_sk) per_customer) ranked
  where ssales > ([TOPPERCENT]/100.0) * tpcds_cmax)
 [_LIMITA] select [_LIMITB] sum(sales)
 from (select cs_quantity*cs_list_price sales
             ,cs_item_sk sold_item_sk
             ,cs_bill_customer_sk sold_cust_sk
       from catalog_sales
           ,date_dim
       where d_year = [YEAR]
         and d_moy = [MONTH]
         and cs_sold_date_sk = d_date_sk
      union all
      select ws_quantity*ws_list_price
            ,ws_item_sk
            ,ws_bill_customer_sk
       from web_sales
           ,date_dim
       where d_year = [YEAR]
         and d_moy = [MONTH]
         and ws_sold_date_sk = d_date_sk) all_sales
 where sold_item_sk in (select item_sk from frequent_ss_items)
   and sold_cust_sk in (select c_customer_sk from best_ss_customer)
 [_LIMITC];

 with frequent_ss_items as
 (select i_item_sk item_sk
  from store_sales
      ,date_dim
      ,item
  where ss_sold_date_sk = d_date_sk
    and ss_item_sk = i_item_sk
    and d_year in ([YEAR],[YEAR]+1,[YEAR]+2,[YEAR]+3)
  group by i_item_sk,d_date
  having count(*) >4),
 best_ss_customer as
 (select c_customer_sk
  from (select c_customer_sk, ssales, max(csales) over () tpcds_cmax
        from (select c_customer_sk,
                     sum(ss_quantity*ss_sales_price) ssales,
                     sum(case when d_year in ([YEAR],[YEAR]+1,[YEAR]+2,[YEAR]+3)
                              then ss_quantity*ss_sales_price end) csales
              from store_sales
                   join customer on ss_customer_sk = c_customer_sk
                   left join date_dim on ss_sold_date_sk = d_date_sk
              group by c_customer_sk) per_customer) ranked
  where ssales > ([TOPPERCENT]/100.0) * tpcds_cmax)
 [_LIMITA] select [_LIMITB] c_last_name,c_first_name,sales
 from (select c_last_name,c_first_name,sum(sales) sales
       from (select 1 channel
                   ,cs_bill_customer_sk sold_cust_sk
                   ,cs_item_sk sold_item_sk
                   ,cs_quantity*cs_list_price sales
             from catalog_sales
                 ,date_dim
             where d_year = [YEAR]
               and d_moy = [MONTH]
               and cs_sold_date_sk = d_date_sk
            union all
            select 2
                  ,ws_bill_customer_sk
                  ,ws_item_sk
                  ,ws_quantity*ws_list_price
             from web_sales
                 ,date_dim
             where d_year = [YEAR]
               and d_moy = [MONTH]
               and ws_sold_date_sk = d_date_sk) all_sales
           ,customer
       where sold_item_sk in (select item_sk from frequent_ss_items)
         and sold_cust_sk in (select c_customer_sk from best_ss_customer)
         and sold_cust_sk = c_customer_sk
       group by channel,c_last_name,c_first_name) by_channel
 order by c_last_name,c_first_name,sales
 [_LIMITC];
