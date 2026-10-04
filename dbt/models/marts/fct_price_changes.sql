-- Un evento por cada cambio de precio, precio de lista o disponibilidad de un producto.
select *
from {{ ref('stg_turso__prices') }}
