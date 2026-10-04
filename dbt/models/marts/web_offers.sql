-- Precio de cada producto de web_products en cada tienda donde se vende (la mejor oferta de la tienda).
-- is_price_outlier marca los productos donde la tienda más cara cuesta más de 3 veces la más barata:
-- probablemente el código de barras agrupa presentaciones distintas y no conviene mostrar un ahorro.
with matched as (
    select
        canonical_product_id as product_id,
        store_id,
        store_name,
        store_product_id,
        store_product_name,
        url,
        price,
        list_price,
        discount_pct,
        is_available,
        price_since
    from {{ ref('int_offers__best_per_store') }}
),

unmatched as (
    select
        concat('sku-', p.store_product_id) as product_id,
        p.store_id,
        p.store_name,
        p.store_product_id,
        p.product_name as store_product_name,
        p.url,
        c.price,
        c.list_price,
        c.discount_pct,
        c.is_available,
        c.price_since
    from {{ ref('dim_products') }} p
    join {{ ref('fct_current_prices') }} c on c.store_product_id = p.store_product_id
    where p.canonical_product_id is null
),

offers as (
    select * from matched
    union all
    select * from unmatched
)

select
    concat(product_id, '|', store_id) as offer_key,
    *,
    coalesce(
        max(case when is_available and price > 0 then price end) over (partition by product_id)
        / nullif(min(case when is_available and price > 0 then price end) over (partition by product_id), 0) > 3,
        false
    ) as is_price_outlier
from offers
