
with wss as
 (select d_week_seq,
        ss_store_sk,
        sum(ss_sales_price) filter (where d_day_name='Sunday') sun_sales,
        sum(ss_sales_price) filter (where d_day_name='Monday') mon_sales,
        sum(ss_sales_price) filter (where d_day_name='Tuesday') tue_sales,
        sum(ss_sales_price) filter (where d_day_name='Wednesday') wed_sales,
        sum(ss_sales_price) filter (where d_day_name='Thursday') thu_sales,
        sum(ss_sales_price) filter (where d_day_name='Friday') fri_sales,
        sum(ss_sales_price) filter (where d_day_name='Saturday') sat_sales
 from store_sales,date_dim
 where d_date_sk = ss_sold_date_sk
   and d_week_seq in (select d_week_seq from date_dim
                      where d_month_seq between 1185 and 1185 + 23)
 group by d_week_seq,ss_store_sk
 )
  select  s_store_name1,s_store_id1,d_week_seq1
       ,sun_sales1/sun_sales2,mon_sales1/mon_sales2
       ,tue_sales1/tue_sales2,wed_sales1/wed_sales2,thu_sales1/thu_sales2
       ,fri_sales1/fri_sales2,sat_sales1/sat_sales2
 from
 (select s_store_name s_store_name1,wss.d_week_seq d_week_seq1
        ,s_store_id s_store_id1,sun_sales sun_sales1
        ,mon_sales mon_sales1,tue_sales tue_sales1
        ,wed_sales wed_sales1,thu_sales thu_sales1
        ,fri_sales fri_sales1,sat_sales sat_sales1
  from wss,store,date_dim d
  where d.d_week_seq = wss.d_week_seq and
        ss_store_sk = s_store_sk and
        d_month_seq between 1185 and 1185 + 11) y,
 (select s_store_name s_store_name2,wss.d_week_seq d_week_seq2
        ,s_store_id s_store_id2,sun_sales sun_sales2
        ,mon_sales mon_sales2,tue_sales tue_sales2
        ,wed_sales wed_sales2,thu_sales thu_sales2
        ,fri_sales fri_sales2,sat_sales sat_sales2
  from wss,store,date_dim d
  where d.d_week_seq = wss.d_week_seq and
        ss_store_sk = s_store_sk and
        d_month_seq between 1185+ 12 and 1185 + 23) x
 where s_store_id1=s_store_id2
   and d_week_seq1=d_week_seq2-52
 order by s_store_name1,s_store_id1,d_week_seq1
limit 100;


