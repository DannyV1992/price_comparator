-- Una fila por descarga de una tienda, con su estado y duración.
select
    r.run_id,
    r.store_id,
    s.store_name,
    r.started_at,
    r.finished_at,
    r.duration_minutes,
    r.status,
    r.products_seen,
    r.notes
from {{ ref('stg_turso__scrape_runs') }} r
join {{ ref('dim_stores') }} s on s.store_id = r.store_id
