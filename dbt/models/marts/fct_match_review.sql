-- Cruces por nombre dudosos pendientes de revisión. Para decidir uno, agrega una fila al seed
-- dbt/seeds/match_overrides.csv con su product_key, el canonical_product_id y la decisión
-- (confirmed o rejected); al siguiente dbt build desaparece de esta lista.
select
    p.product_key,
    p.store_name,
    p.product_name,
    p.brand,
    m.canonical_product_id,
    c.canonical_name,
    c.canonical_brand,
    m.score,
    m.next_score,
    m.brand_match,
    m.variant_conflict
from {{ ref('int_products__matched_by_name') }} m
join {{ ref('int_products__enriched') }} p on p.store_product_id = m.store_product_id
join {{ ref('int_products__matched_by_ean') }} c on c.canonical_product_id = m.canonical_product_id
left join (select distinct product_key from {{ ref('match_overrides') }}) o on o.product_key = p.product_key
where m.confidence = 'review' and o.product_key is null
