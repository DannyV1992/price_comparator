select
    id as run_id,
    store_id,
    try_cast(started_at as timestamp) as started_at,
    try_cast(finished_at as timestamp) as finished_at,
    round((unix_timestamp(try_cast(finished_at as timestamp)) - unix_timestamp(try_cast(started_at as timestamp))) / 60, 1)
        as duration_minutes,
    status,
    products_seen,
    notes
from {{ source('turso', 'scrape_runs') }}
