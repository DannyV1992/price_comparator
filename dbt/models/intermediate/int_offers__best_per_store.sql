-- La mejor oferta de cada tienda para cada producto canónico. Una tienda puede tener varios SKUs con
-- el mismo código de barras (sobre todo Walmart): se queda el disponible y, de ellos, el más barato.
select
    concat(m.canonical_product_id, '|', p.store_id) as offer_key,
    m.canonical_product_id,
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
from {{ ref('int_products__enriched') }} p
join {{ ref('int_products__matched_by_ean') }} m on m.ean_key = p.ean_key
join {{ ref('int_prices__latest') }} c on c.store_product_id = p.store_product_id
qualify row_number() over (
    partition by m.canonical_product_id, p.store_id
    order by
        case when c.is_available and c.price is not null then 0 else 1 end,
        c.price asc nulls last,
        p.store_product_id
) = 1
