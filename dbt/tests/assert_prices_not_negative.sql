-- Un precio nunca puede ser negativo.
select price_id, price, list_price
from {{ ref('prices') }}
where price < 0 or list_price < 0
