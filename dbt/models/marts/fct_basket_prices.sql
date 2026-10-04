-- Costo de cada canasta (seed basket_items) por tienda y día. Una canasta solo se puede comparar entre
-- tiendas cuando está completa (la tienda vende y tiene en existencia todos sus productos): basket_total
-- suma solo los productos disponibles, is_complete dice si estaban todos, y cheapest_rank ordena las
-- tiendas con la canasta completa de la más barata a la más cara.
with items as (
    select * from {{ ref('basket_items') }}
),

basket_size as (
    select basket_name, count(*) as n_items
    from items
    group by basket_name
),

priced as (
    select
        i.basket_name,
        d.date_day,
        d.store_id,
        count(*) as n_items_priced,
        sum(i.quantity * d.price) as basket_total
    from items i
    join {{ ref('int_prices__daily_best_per_store') }} d on d.canonical_product_id = i.canonical_product_id
    group by i.basket_name, d.date_day, d.store_id
),

final as (
    select
        concat(p.basket_name, '|', p.date_day, '|', p.store_id) as basket_key,
        p.basket_name,
        p.date_day,
        p.store_id,
        s.store_name,
        b.n_items,
        p.n_items_priced,
        p.basket_total,
        p.n_items_priced = b.n_items as is_complete
    from priced p
    join basket_size b on b.basket_name = p.basket_name
    join {{ ref('dim_stores') }} s on s.store_id = p.store_id
)

select
    *,
    case
        when is_complete then rank() over (partition by basket_name, date_day, is_complete order by basket_total)
    end as cheapest_rank
from final
