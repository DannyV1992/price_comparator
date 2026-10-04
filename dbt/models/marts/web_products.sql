-- Productos que se pueden elegir en la web: un producto canónico por fila, más cada producto que no se pudo
-- cruzar con otra tienda (se trata como un producto de una sola tienda, con id 'sku-<store_product_id>').
-- Sin esos últimos, tiendas como Automercado casi no aparecerían en la web.
with canonical as (
    select
        c.canonical_product_id as product_id,
        c.canonical_name as product_name,
        c.canonical_brand as brand,
        c.n_stores,
        max(p.image_url) as image_url,
        max(p.category_name) as category_name
    from {{ ref('dim_canonical_products') }} c
    join {{ ref('dim_products') }} p on p.canonical_product_id = c.canonical_product_id
    group by c.canonical_product_id, c.canonical_name, c.canonical_brand, c.n_stores
),

unmatched as (
    select
        concat('sku-', store_product_id) as product_id,
        product_name,
        brand,
        1 as n_stores,
        image_url,
        category_name
    from {{ ref('dim_products') }}
    where canonical_product_id is null
)

select * from canonical
union all
select * from unmatched
