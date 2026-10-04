select
    id as store_id,
    name as store_name,
    website
from {{ source('turso', 'stores') }}
