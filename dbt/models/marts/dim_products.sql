-- Un producto por SKU de tienda. ean_key sirve para cruzar productos entre tiendas.
select *
from {{ ref('int_products__enriched') }}
