-- Para cada día, producto canónico y tienda: el precio más bajo entre sus SKUs disponibles ese día.
-- Es la base de los índices y las canastas: solo cuentan productos cruzados entre tiendas y con existencias.
select
    d.date_day,
    a.canonical_product_id,
    p.store_id,
    min(v.price) as price
from {{ ref('int_prices__validity') }} v
join {{ ref('all_dates') }} d on d.date_day between v.valid_from and v.valid_to
join {{ ref('int_products__canonical_assignment') }} a on a.store_product_id = v.store_product_id
join {{ ref('int_products__enriched') }} p on p.store_product_id = v.store_product_id
where v.is_available and v.price > 0
group by d.date_day, a.canonical_product_id, p.store_id
