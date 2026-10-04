-- A qué producto canónico pertenece cada producto de tienda, y con qué método:
--   manual : decisión confirmada en el seed match_overrides (gana sobre todo lo demás)
--   ean    : mismo código de barras normalizado
--   name   : cruce por nombre con confianza 'high' (salvo que el seed lo rechace)
-- Un producto sin fila aquí todavía no se pudo cruzar con otras tiendas.
with ean as (
    select p.store_product_id, m.canonical_product_id, 'ean' as match_method, cast(1.0 as double) as match_score
    from {{ ref('int_products__enriched') }} p
    join {{ ref('int_products__matched_by_ean') }} m on m.ean_key = p.ean_key
),

rejected as (
    select product_key, canonical_product_id
    from {{ ref('match_overrides') }}
    where decision = 'rejected'
),

by_name as (
    select p.store_product_id, m.canonical_product_id, 'name' as match_method, cast(m.score as double) as match_score
    from {{ ref('int_products__matched_by_name') }} m
    join {{ ref('int_products__enriched') }} p on p.store_product_id = m.store_product_id
    left join rejected r on r.product_key = p.product_key and r.canonical_product_id = m.canonical_product_id
    where m.confidence = 'high' and r.product_key is null
),

manual as (
    select p.store_product_id, o.canonical_product_id, 'manual' as match_method, cast(1.0 as double) as match_score
    from {{ ref('match_overrides') }} o
    join {{ ref('int_products__enriched') }} p on p.product_key = o.product_key
    where o.decision = 'confirmed'
),

unioned as (
    select * from manual
    union all select * from ean
    union all select * from by_name
)

select store_product_id, canonical_product_id, match_method, match_score
from unioned
qualify row_number() over (
    partition by store_product_id
    order by case match_method when 'manual' then 1 when 'ean' then 2 else 3 end
) = 1
