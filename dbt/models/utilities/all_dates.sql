-- Calendario: un día por fila, desde el primer precio guardado hasta hoy. Sirve para rellenar los días en
-- que un precio no cambió (Turso guarda solo los cambios) y para agrupar por semana o mes en BI.
with days as (
    select explode(sequence(first_day, current_date(), interval 1 day)) as date_day
    from (
        select min(cast(scraped_at as date)) as first_day
        from {{ ref('stg_turso__prices') }}
    )
)

select
    date_day,
    year(date_day) as year,
    month(date_day) as month,
    date_format(date_day, 'yyyy-MM') as year_month,
    weekofyear(date_day) as week_of_year,
    dayofweek(date_day) as day_of_week_number,  -- 1 = domingo
    date_format(date_day, 'EEEE') as day_name,
    dayofweek(date_day) in (1, 7) as is_weekend
from days
