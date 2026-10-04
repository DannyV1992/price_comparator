-- Un precio nunca puede ser negativo.
select price_id, price, list_price
from {{ ref('fct_price_changes') }}
where price < 0 or list_price < 0
