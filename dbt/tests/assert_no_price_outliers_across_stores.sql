{{ config(severity='warn') }}
-- Aviso (no error): productos cuyo precio difiere más de 3 veces entre tiendas. Casi siempre es un código
-- de barras compartido por presentaciones distintas; conviene revisarlos a mano.
select distinct canonical_product_id, min_price
from {{ ref('fct_price_comparison') }}
where is_price_outlier
