-- Un producto canónico por código de barras normalizado. Los SKUs de distintas tiendas con el mismo
-- ean_key son el mismo producto. Nombre y marca comunes: el valor que más tiendas repiten (en
-- empate, el nombre más largo), porque cada tienda escribe el nombre a su manera y algunas ponen
-- en marca al fabricante y no a la marca del producto.
with products as (
    select *
    from {{ ref('int_products__enriched') }}
    where ean_key is not null
),

name_votes as (
    select
        ean_key,
        product_name,
        row_number() over (
            partition by ean_key
            order by count(*) desc, length(product_name) desc, product_name
        ) as rn
    from products
    group by ean_key, product_name
),

brand_votes as (
    select
        ean_key,
        brand,
        row_number() over (partition by ean_key order by count(*) desc, brand) as rn
    from products
    where brand is not null
    group by ean_key, brand
),

totals as (
    select
        ean_key,
        count(distinct store_id) as n_stores,
        count(*) as n_skus
    from products
    group by ean_key
)

select
    concat('ean:', t.ean_key) as canonical_product_id,
    t.ean_key,
    n.product_name as canonical_name,
    b.brand as canonical_brand,
    t.n_stores,
    t.n_skus,
    'ean' as match_method
from totals t
join name_votes n on n.ean_key = t.ean_key and n.rn = 1
left join brand_votes b on b.ean_key = t.ean_key and b.rn = 1
