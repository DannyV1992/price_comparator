select
    r.id as run_id,
    r.store_id,
    s.store_name,
    try_cast(r.started_at as timestamp) as started_at,
    try_cast(r.finished_at as timestamp) as finished_at,
    round((unix_timestamp(try_cast(r.finished_at as timestamp)) - unix_timestamp(try_cast(r.started_at as timestamp))) / 60, 1)
        as duration_minutes,
    r.status,
    r.products_seen,
    r.notes
from {{ source('raw', 'scrape_runs') }} r
join {{ ref('stores') }} s on s.store_id = r.store_id
