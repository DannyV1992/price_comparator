-- Un producto por SKU de tienda. canonical_product_id lo une con el mismo producto de otras tiendas
-- (NULL si todavía no se pudo cruzar).
select
    p.*,
    m.canonical_product_id
from {{ ref('int_products__enriched') }} p
left join {{ ref('int_products__matched_by_ean') }} m on m.ean_key = p.ean_key
