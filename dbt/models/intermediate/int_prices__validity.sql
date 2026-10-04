-- Cada precio con el rango de días en que estuvo vigente. Turso guarda solo los cambios, así que un
-- precio vale desde el día en que se registró hasta el día antes del siguiente cambio; el último llega
-- hasta la última vez que se vio el producto en el catálogo (no se inventan días de productos que ya
-- no se venden). Si hubo varios cambios el mismo día, cuenta el último.
with daily as (
    select
        *,
        cast(scraped_at as date) as valid_from
    from {{ ref('stg_turso__prices') }}
    qualify row_number() over (
        partition by store_product_id, cast(scraped_at as date)
        order by scraped_at desc, price_id desc
    ) = 1
),

ranged as (
    select
        *,
        lead(valid_from) over (partition by store_product_id order by valid_from) as next_from
    from daily
)

select
    r.price_id,
    r.store_product_id,
    r.price,
    r.list_price,
    r.is_available,
    r.discount_pct,
    r.valid_from,
    coalesce(date_sub(r.next_from, 1), least(cast(p.last_seen_at as date), current_date())) as valid_to
from ranged r
join {{ ref('stg_turso__store_products') }} p on p.store_product_id = r.store_product_id
