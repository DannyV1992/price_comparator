-- Propuesta de cruce por nombre para los productos sin código de barras (y el mejor candidato de cada uno).
-- Cada producto sin código se compara con los productos que sí tienen código, de OTRAS tiendas y con el
-- MISMO tamaño (size_key); el parecido es la proporción de palabras del nombre que comparten (Jaccard).
-- Un producto nunca se cruza con un producto canónico que ya tiene un SKU de su propia tienda.
--   confidence = 'high'   : parecido alto, misma marca, claramente mejor que el siguiente candidato y sin
--                           diferencias de variante (género, sabor, versión) ni de piezas por paquete
--   confidence = 'review' : plausible pero dudoso; se revisa a mano (fct_match_review -> seed match_overrides)
-- Para precios es peor un cruce falso que uno que falta, por eso 'high' es estricto.
with unmatched as (
    select *
    from {{ ref('int_products__parsed') }}
    where ean_key is null and size_key is not null and size(name_tokens) > 0
),

anchors as (
    select p.*, m.canonical_product_id
    from {{ ref('int_products__parsed') }} p
    join {{ ref('int_products__matched_by_ean') }} m on m.ean_key = p.ean_key
    where p.size_key is not null
),

canonical_stores as (
    select canonical_product_id, collect_set(store_id) as store_ids
    from anchors
    group by canonical_product_id
),

pairs as (
    select
        u.store_product_id,
        u.store_id,
        a.canonical_product_id,
        size(array_intersect(u.name_tokens, a.name_tokens)) as common_tokens,
        size(array_union(u.name_tokens, a.name_tokens)) as total_tokens,
        array_except(array_union(u.name_tokens, a.name_tokens), array_intersect(u.name_tokens, a.name_tokens)) as differing_tokens,
        coalesce(
            u.brand_norm != '' and a.brand_norm != ''
            and (u.brand_norm = a.brand_norm
                 or u.brand_norm like concat('%', a.brand_norm, '%')
                 or a.brand_norm like concat('%', u.brand_norm, '%')),
            false
        ) as brand_match,
        coalesce(u.pack_count, 1) != coalesce(a.pack_count, 1) as pack_conflict
    from unmatched u
    join anchors a on a.size_key = u.size_key and a.store_id != u.store_id
),

scored as (
    select
        p.store_product_id,
        p.canonical_product_id,
        p.common_tokens / p.total_tokens as score,
        p.brand_match,
        -- palabras que distinguen una variante de otra: si solo una de las dos las tiene, no es el mismo producto
        size(array_intersect(p.differing_tokens, array(
            'hombre', 'mujer', 'femenino', 'masculino', 'dama', 'caballero', 'nino', 'nina', 'bebe', 'men', 'women',
            'light', 'zero', 'cero', 'diet', 'original', 'clasico', 'clasica', 'integral', 'deslactosada',
            'descremada', 'semidescremada', 'entera', 'picante', 'suave', 'regular', 'extra', 'ultra', 'max',
            'vainilla', 'fresa', 'chocolate', 'limon', 'naranja', 'manzana', 'uva', 'pina', 'coco', 'mango',
            'cafe', 'menta', 'cereza', 'durazno', 'melocoton', 'sandia', 'mora', 'frambuesa', 'tamarindo',
            'blanco', 'blanca', 'negro', 'negra', 'rojo', 'roja', 'verde', 'amarillo', 'azul', 'rosado',
            'leche', 'sal', 'dulce', 'natural', 'organico', 'organica', 'sin', 'azucar', 'gas', 'mini'
        ))) > 0 or p.pack_conflict as variant_conflict
    from pairs p
    join canonical_stores cs on cs.canonical_product_id = p.canonical_product_id
    where p.common_tokens >= 2
      and not array_contains(cs.store_ids, p.store_id)
    qualify row_number() over (
        partition by p.store_product_id, p.canonical_product_id
        order by p.common_tokens / p.total_tokens desc
    ) = 1
),

ranked as (
    select
        *,
        row_number() over (partition by store_product_id order by score desc, brand_match desc, canonical_product_id) as rn,
        lead(score) over (partition by store_product_id order by score desc, brand_match desc, canonical_product_id) as next_score
    from scored
    where score >= 0.4
)

select
    store_product_id,
    canonical_product_id,
    round(score, 3) as score,
    brand_match,
    variant_conflict,
    round(next_score, 3) as next_score,
    case
        when coalesce(score - next_score, 1) >= 0.1
             and not variant_conflict
             and ((brand_match and score >= 0.6) or score >= 0.8) then 'high'
        else 'review'
    end as confidence
from ranked
where rn = 1
