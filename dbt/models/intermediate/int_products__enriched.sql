-- Productos con el nombre de su tienda y de su categoría.
select
    p.store_product_id,
    p.product_key,
    p.store_id,
    s.store_name,
    p.store_item_id,
    p.product_name,
    p.brand,
    p.ean_raw,
    p.ean_key,
    p.store_category_id,
    c.category_name,
    p.unit,
    p.unit_multiplier,
    p.url,
    p.image_url,
    p.first_seen_at,
    p.last_seen_at
from {{ ref('stg_turso__store_products') }} p
join {{ ref('stg_turso__stores') }} s on s.store_id = p.store_id
left join {{ ref('stg_turso__categories') }} c
    on c.store_id = p.store_id and c.store_category_id = p.store_category_id
