-- Historial de precios tal como se guarda: una fila cuando cambia el precio, el precio de lista o la
-- disponibilidad del producto. Más x Menos publica 0 cuando un producto está agotado: eso no es un
-- precio, así que se vuelve NULL (la disponibilidad queda en is_available).
select
    id as price_id,
    store_product_id,
    run_id,
    try_cast(scraped_at as timestamp) as scraped_at,
    nullif(price, 0) as price,
    nullif(list_price, 0) as list_price,
    coalesce(available_qty, 0) > 0 as is_available,
    case
        when price > 0 and list_price > price then round(100 * (list_price - price) / list_price, 1)
    end as discount_pct
from {{ source('raw', 'prices') }}
