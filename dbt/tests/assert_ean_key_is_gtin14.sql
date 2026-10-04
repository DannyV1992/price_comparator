-- La clave de código de barras, cuando existe, tiene siempre 14 dígitos.
select store_product_id, ean_raw, ean_key
from {{ ref('dim_products') }}
where ean_key is not null and (length(ean_key) != 14 or ean_key rlike '[^0-9]')
