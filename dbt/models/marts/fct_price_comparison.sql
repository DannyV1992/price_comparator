-- Comparación de precios: una fila por producto canónico y tienda, solo para productos que se venden en
-- al menos dos tiendas. min_price es el precio más bajo entre las ofertas disponibles; is_price_outlier
-- marca los productos donde la diferencia entre tiendas es tan grande (más de 3 veces) que el código de
-- barras probablemente agrupa productos distintos, por ejemplo presentaciones de distinto tamaño.
with offers as (
    select
        *,
        min(case when is_available and price is not null then price end)
            over (partition by canonical_product_id) as min_price,
        max(case when is_available and price is not null then price end)
            over (partition by canonical_product_id) as max_price,
        count(*) over (partition by canonical_product_id) as n_stores_compared
    from {{ ref('int_offers__best_per_store') }}
)

select
    offer_key,
    canonical_product_id,
    store_id,
    store_name,
    store_product_id,
    store_product_name,
    url,
    price,
    list_price,
    discount_pct,
    is_available,
    price_since,
    min_price,
    is_available and price = min_price as is_cheapest,
    case when is_available and price is not null and min_price > 0
         then round(100 * (price - min_price) / min_price, 1) end as pct_above_min,
    n_stores_compared,
    coalesce(max_price / nullif(min_price, 0) > 3, false) as is_price_outlier
from offers
where n_stores_compared >= 2
