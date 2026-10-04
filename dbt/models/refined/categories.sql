select
    concat(store_id, '|', store_category_id) as category_key,
    store_id,
    store_category_id,
    name as category_name,
    parent_store_category_id,
    level as category_level
from {{ source('raw', 'categories') }}
