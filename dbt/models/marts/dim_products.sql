-- Un producto por SKU de tienda. canonical_product_id lo une con el mismo producto de otras tiendas
-- (NULL si todavía no se pudo cruzar); match_method dice cómo se cruzó (ean, name o manual).
select
    p.*,
    a.canonical_product_id,
    a.match_method,
    a.match_score
from {{ ref('int_products__enriched') }} p
left join {{ ref('int_products__canonical_assignment') }} a on a.store_product_id = p.store_product_id
