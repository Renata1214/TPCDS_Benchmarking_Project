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
 define YEAR=random(1999,2001,uniform);
 define _LIMIT=100;
 define SELECTONE= text({"i_category",1},{"i_brand",1},{"i_category, i_brand",1},{"s_store_name",1},{"s_company_name",1},{"s_store_name, s_company_name",1},{"i_category, i_brand, s_store_name, s_company_name",1});
 define SELECTTWO= text({",d_year",1},{",d_year, d_moy",1});
 define ORDERBY= text({"avg_monthly_sales",1},{"sum_sales",1},{"psum",1},{"nsum",1});

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
           d_year = [YEAR]
           or (d_year = [YEAR]-1 and d_moy = 12)
           or (d_year = [YEAR]+1 and d_moy = 1)
       )
     group by i_category, i_brand,
              s_store_name, s_company_name,
              d_year, d_moy
 ),
 v2 as (
     select [SELECTONE]
            [SELECTTWO]
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
 [_LIMITA] select
[_LIMITB]
        [SELECTONE]
        [SELECTTWO]
        ,avg_monthly_sales
        ,sum_sales
        ,psum
        ,nsum
 from v2
 where d_year = [YEAR]
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
 order by sum_sales - avg_monthly_sales, [ORDERBY]
 [_LIMITC];
