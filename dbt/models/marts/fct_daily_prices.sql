-- Precio vigente de cada producto en cada día (una fila por producto y día), listo para graficar la
-- evolución. Se arma cruzando el calendario con los rangos de vigencia de cada precio.
select
    concat(v.store_product_id, '|', cast(d.date_day as string)) as daily_price_key,
    d.date_day,
    v.store_product_id,
    p.store_id,
    p.canonical_product_id,
    v.price,
    v.list_price,
    v.discount_pct,
    v.is_available
from {{ ref('int_prices__validity') }} v
join {{ ref('all_dates') }} d on d.date_day between v.valid_from and v.valid_to
join {{ ref('dim_products') }} p on p.store_product_id = v.store_product_id
