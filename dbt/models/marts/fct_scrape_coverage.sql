-- Por descarga y categoría: lo que el sitio decía tener frente a lo que se bajó. Sirve para vigilar la
-- calidad de los datos. Ojo: en VTEX (Más x Menos, Walmart, Maxi Pali) una categoría grande queda topada
-- en 2.550 resultados y se completa por sus subcategorías, así que una fila con is_complete = false no
-- implica que falten productos; el total de la descarga está en fct_scrape_runs.
select
    concat(c.run_id, '|', c.category_path) as coverage_key,
    c.run_id,
    r.store_id,
    r.store_name,
    r.started_at,
    c.category_path,
    c.category_name,
    c.reported_total,
    c.downloaded,
    c.retries,
    round(100 * c.downloaded / nullif(c.reported_total, 0), 1) as coverage_pct,
    c.downloaded >= c.reported_total as is_complete
from {{ ref('stg_turso__scrape_run_categories') }} c
join {{ ref('fct_scrape_runs') }} r on r.run_id = c.run_id
