-- Un producto por SKU de tienda, con el código de barras normalizado para cruzar entre tiendas.
select
    p.id as store_product_id,
    concat(p.store_id, '|', p.store_item_id) as product_key,
    p.store_id,
    s.store_name,
    p.store_item_id,
    p.name as product_name,
    p.brand,
    nullif(trim(p.ean), '') as ean_raw,
    {{ normalize_ean('p.ean') }} as ean_key,
    p.store_category_id,
    c.category_name,
    p.unit,
    p.unit_multiplier,
    p.url,
    p.image_url,
    try_cast(p.first_seen as timestamp) as first_seen_at,
    try_cast(p.last_seen as timestamp) as last_seen_at
from {{ source('raw', 'store_products') }} p
join {{ ref('stores') }} s on s.store_id = p.store_id
left join {{ ref('categories') }} c
    on c.store_id = p.store_id and c.store_category_id = p.store_category_id
