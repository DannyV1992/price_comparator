-- Productos canónicos: el mismo producto visto en una o varias tiendas. Por ahora se cruzan por código
-- de barras; los productos sin código (Automercado, PriceSmart, Pequeño Mundo) se agregarán después.
select *
from {{ ref('int_products__matched_by_ean') }}
