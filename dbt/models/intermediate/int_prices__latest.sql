-- Último estado de precio conocido de cada producto.
select
    store_product_id,
    price,
    list_price,
    is_available,
    discount_pct,
    scraped_at as price_since
from (
    select
        *,
        row_number() over (partition by store_product_id order by scraped_at desc, price_id desc) as rn
    from {{ ref('stg_turso__prices') }}
)
where rn = 1
