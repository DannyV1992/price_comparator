-- Un SKU de tienda por fila. ean_key es el código de barras normalizado para cruzar entre tiendas.
select
    id as store_product_id,
    concat(store_id, '|', store_item_id) as product_key,
    store_id,
    store_item_id,
    name as product_name,
    brand,
    nullif(trim(ean), '') as ean_raw,
    {{ normalize_ean('ean') }} as ean_key,
    store_category_id,
    unit,
    unit_multiplier,
    url,
    image_url,
    try_cast(first_seen as timestamp) as first_seen_at,
    try_cast(last_seen as timestamp) as last_seen_at
from {{ source('turso', 'store_products') }}
