{{ config(severity='warn') }}
-- Aviso (no error) si la última descarga terminada de alguna tienda no quedó en estado 'ok'.
select store_name, run_id, status, started_at, notes
from (
    select
        *,
        row_number() over (partition by store_id order by started_at desc) as rn
    from {{ ref('fct_scrape_runs') }}
    where status not in ('running', 'syncing')
)
where rn = 1 and status != 'ok'
