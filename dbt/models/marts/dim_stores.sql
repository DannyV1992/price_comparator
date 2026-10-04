select
    s.store_id,
    s.store_name,
    s.website,
    i.store_type
from {{ ref('stg_turso__stores') }} s
left join {{ ref('store_info') }} i on i.store_name = s.store_name
