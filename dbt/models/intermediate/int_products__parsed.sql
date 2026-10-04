-- Nombre normalizado, tamaño y marca de cada producto, para comparar productos por nombre.
--   size_key: cantidad normalizada ('750ml', '333g', '80unit'); sale del nombre, con el primer volumen o
--             peso que aparece (las tiendas lo escriben como '750 ml', '750ML', '0.75 L'...). Si no hay
--             volumen ni peso, se usa el conteo de unidades ('80U', '25 sobres'). NULL si no se encuentra.
--   pack_count: piezas por paquete que dice el nombre ('6 Unidades', '4 pack'); NULL si no dice.
--   name_tokens: palabras del nombre sin tildes, sin medidas ni palabras de relleno.
with cleaned as (
    select
        *,
        translate(lower(product_name), 'áéíóúüñ', 'aeiouun') as name_clean
    from {{ ref('int_products__enriched') }}
),

measured as (
    select
        *,
        -- multipack: '6 x 355 ml' -> 6 veces 355
        try_cast(nullif(regexp_extract(name_clean, '([0-9]+)[ ]?x[ ]?([0-9]+(?:[.,][0-9]+)?)[ ]?(ml|cc|litros?|lts?|lt|l|kgs?|kilos?|gramos?|grs?|gr|g)(?![a-z])', 1), '') as double) as pack_multiplier,
        regexp_extract(name_clean, '([0-9]+(?:[.,][0-9]+)?)[ ]?(ml|cc|litros?|lts?|lt|l|kgs?|kilogramos?|kilos?|gramos?|grs?|gr|g|libras?|lbs?|lb|oz)(?![a-z])', 1) as measure_text,
        regexp_extract(name_clean, '([0-9]+(?:[.,][0-9]+)?)[ ]?(ml|cc|litros?|lts?|lt|l|kgs?|kilogramos?|kilos?|gramos?|grs?|gr|g|libras?|lbs?|lb|oz)(?![a-z])', 2) as measure_unit,
        regexp_extract(name_clean, '([0-9]+)[ ]?(u|un|unid|unids|und|unds|unidad|unidades|sobres?|pcs|pzas|piezas)(?![a-z])', 1) as count_text,
        regexp_extract(name_clean, '([0-9]+)[ ]?(pack|packs)(?![a-z])', 1) as pack_text
    from cleaned
),

based as (
    select
        *,
        try_cast(replace(measure_text, ',', '.') as double) * coalesce(pack_multiplier, 1) as measure_value,
        case
            when measure_unit in ('ml', 'cc') then 'ml'
            when measure_unit rlike '^(l|lt|lts|litro|litros)$' then 'ml'
            when measure_unit rlike '^(g|gr|grs|gramo|gramos)$' then 'g'
            when measure_unit rlike '^(kg|kgs|kilo|kilos|kilogramo|kilogramos)$' then 'g'
            when measure_unit rlike '^(lb|lbs|libra|libras)$' then 'g'
            when measure_unit = 'oz' then 'oz'
        end as size_unit_base,
        case
            when measure_unit rlike '^(l|lt|lts|litro|litros|kg|kgs|kilo|kilos|kilogramo|kilogramos)$' then 1000
            when measure_unit rlike '^(lb|lbs|libra|libras)$' then 453.592
            else 1
        end as to_base
    from measured
),

sized as (
    select
        *,
        case
            when size_unit_base is not null and measure_value > 0
                then concat(cast(round(measure_value * to_base) as bigint), size_unit_base)
            when count_text != '' then concat(cast(count_text as bigint), 'unit')
        end as size_key
    from based
),

tokenized as (
    select
        *,
        filter(
            array_distinct(split(trim(regexp_replace(name_clean, '[^a-z0-9]+', ' ')), ' ')),
            t -> length(t) > 1
                and t not rlike '^[0-9]+$'
                and not array_contains(array('de', 'del', 'la', 'el', 'los', 'las', 'en', 'con', 'para', 'por',
                    'una', 'unidad', 'unidades', 'unid', 'und', 'unds', 'paquete', 'botella', 'caja', 'bolsa',
                    'lata', 'frasco', 'pack', 'tubo', 'doypack', 'doy', 'sobre', 'sobres', 'gr', 'grs', 'kg', 'ml',
                    'lt', 'lts', 'oz', 'lb', 'pcs', 'cc'), t)
                and t not rlike '^[0-9]+(ml|cc|l|lt|g|gr|kg|oz|lb|u|un|unid)$'
        ) as name_tokens,
        trim(regexp_replace(translate(lower(brand), 'áéíóúüñ', 'aeiouun'), '[^a-z0-9]+', ' ')) as brand_norm
    from sized
)

select
    store_product_id,
    store_id,
    store_name,
    product_name,
    brand,
    brand_norm,
    ean_key,
    size_key,
    try_cast(coalesce(nullif(count_text, ''), nullif(pack_text, '')) as int) as pack_count,
    name_tokens
from tokenized
