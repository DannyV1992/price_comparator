-- Precio vigente de cada producto (una fila por producto).
select *
from {{ ref('int_prices__latest') }}
