
with item_inventory as (
    select inv_item_sk
          ,sum(inv_quantity_on_hand) as quantity_sum
          ,count(inv_quantity_on_hand) as quantity_count
    from inventory
    join date_dim
      on inv_date_sk = d_date_sk
    where d_month_seq between 1212 and 1212 + 11
    group by inv_item_sk
)
 select  i_product_name
             ,i_brand
             ,i_class
             ,i_category
             ,sum(quantity_sum) / nullif(sum(quantity_count), 0) qoh
       from item_inventory
       join item
         on inv_item_sk = i_item_sk
       group by rollup(i_product_name
                       ,i_brand
                       ,i_class
                       ,i_category)
order by qoh, i_product_name, i_brand, i_class, i_category
limit 100;


