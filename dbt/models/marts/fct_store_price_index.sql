-- Índice de precios por tienda y día. Para cada producto que venden al menos 3 tiendas ese día se toma la
-- mediana de sus precios; el índice de una tienda es la media geométrica de (su precio / la mediana) sobre
-- los productos que vende, por 100. 100 = en la mediana del mercado, menos de 100 = más barata, más = más cara.
-- Se excluyen los productos donde la diferencia entre tiendas es de más de 3 veces (códigos compartidos).
-- is_reliable marca las tiendas con suficientes productos comparados (al menos 100) para fiarse del índice.
with daily as (
    select * from {{ ref('int_prices__daily_best_per_store') }}
),

market as (
    select
        date_day,
        canonical_product_id,
        percentile_approx(price, 0.5) as median_price
    from daily
    group by date_day, canonical_product_id
    having count(*) >= 3 and max(price) <= 3 * min(price)
)

select
    concat(d.date_day, '|', d.store_id) as index_key,
    d.date_day,
    d.store_id,
    s.store_name,
    count(*) as n_products,
    round(100 * exp(avg(ln(d.price / m.median_price))), 1) as price_index,
    count(*) >= 100 as is_reliable
from daily d
join market m on m.date_day = d.date_day and m.canonical_product_id = d.canonical_product_id
join {{ ref('dim_stores') }} s on s.store_id = d.store_id
group by d.date_day, d.store_id, s.store_name
