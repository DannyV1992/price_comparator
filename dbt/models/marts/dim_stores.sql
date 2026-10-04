select
    store_id,
    store_name,
    website
from {{ ref('stg_turso__stores') }}
