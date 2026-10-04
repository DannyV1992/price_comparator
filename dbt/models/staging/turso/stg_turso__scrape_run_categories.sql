select
    run_id,
    category_path,
    name as category_name,
    reported_total,
    downloaded,
    retries
from {{ source('turso', 'scrape_run_categories') }}
