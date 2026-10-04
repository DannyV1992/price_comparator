-- Productos canónicos: el mismo producto visto en una o varias tiendas. El nombre y la marca salen del
-- cruce por código de barras; los productos sin código se unen a estos por nombre (o a mano).
with assigned as (
    select
        a.canonical_product_id,
        count(distinct p.store_id) as n_stores,
        count(*) as n_skus,
        array_sort(collect_set(a.match_method)) as match_methods
    from {{ ref('int_products__canonical_assignment') }} a
    join {{ ref('int_products__enriched') }} p on p.store_product_id = a.store_product_id
    group by a.canonical_product_id
)

select
    m.canonical_product_id,
    m.ean_key,
    m.canonical_name,
    m.canonical_brand,
    s.n_stores,
    s.n_skus,
    s.match_methods
from {{ ref('int_products__matched_by_ean') }} m
join assigned s on s.canonical_product_id = m.canonical_product_id
