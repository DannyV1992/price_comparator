# Arquitectura

Comparador histórico de precios de supermercados de Costa Rica. Cada día se descarga el catálogo de
ocho tiendas, se guarda el historial de cambios y se transforma en un modelo listo para analizar.

```mermaid
flowchart LR
    subgraph Fuentes["Tiendas (8)"]
        V[VTEX<br/>Más x Menos · Walmart · Maxi Pali]
        I[Instaleap<br/>Megasuper · Perimercados]
        O[Otras APIs<br/>Pequeño Mundo · Automercado · PriceSmart]
    end

    subgraph GHA["GitHub Actions · diario 09:17 CR"]
        S[Scrapers Python<br/>un trabajo por tienda]
        L[Carga a Databricks]
        D[dbt build]
    end

    T[(Turso<br/>solo cambios de precio)]

    subgraph DBX["Databricks · catálogo supermarket_prices"]
        R[raw<br/>como llega]
        F[refined · dbt staging<br/>limpio y tipado<br/>EAN normalizado]
        I[intermediate · dbt<br/>transformaciones previas]
        A[analytics · dbt marts<br/>dim_ y fct_<br/>productos equivalentes]
    end

    BI[Power BI]
    APP[Demo pública]

    V --> S
    I --> S
    O --> S
    S --> T
    T --> L --> R
    R --> D --> F --> I --> A
    A --> BI
    A --> APP
```

Estado: `raw`, `refined` (staging), `intermediate` y `analytics` están hechas, con el cruce de productos por código
de barras y por nombre, la comparación de precios, el historial diario, el índice de precios por tienda y la
canasta. Power BI y la demo pública están pendientes.

## Decisiones

- **Un trabajo por tienda, en paralelo.** Si un sitio falla, las otras siguen. Cada una termina en rojo
  si su descarga no queda completa.
- **Turso guarda solo cambios.** Una fila nueva en `prices` únicamente cuando cambia el precio, el
  precio de lista o la disponibilidad. Así el historial crece poco.
- **Databricks se carga desde Turso, no desde cada tienda.** Un único proceso escribe en Delta; ocho
  escribiendo a la vez en las mismas tablas chocarían.
- **La carga a Databricks y dbt son trabajos aparte**: si fallan, las descargas ya hechas
  no se pierden, pero la corrida sale en rojo y llega el aviso por correo.
- **Capas y convención de dbt.** Cada capa de dbt tiene su esquema en el catálogo `supermarket_prices`:
  `raw` es una copia fiel de Turso (fechas como texto, ids de Turso); `refined` es *staging* (modelos
  `stg_turso__*`, uno por tabla: renombrar, tipar, limpiar); `intermediate` guarda las transformaciones
  previas (`int_*`) que hagan falta para llegar a los marts; `analytics` son los *marts* (`dim_*` y `fct_*`),
  los que consume Power BI.
- **Clave de cruce entre tiendas: código de barras normalizado.** Sin ceros a la izquierda y
  rellenado a 14 dígitos (GTIN-14). Los códigos de menos de 8 dígitos son de balanza (frutas y
  verduras), no códigos de barras.
- **Cruce por nombre para lo que no tiene código de barras** (Automercado, PriceSmart y Pequeño Mundo).
  `int_products__parsed` extrae el tamaño del nombre (ml, g, unidades, multipacks); `int_products__matched_by_name`
  busca, entre los productos que sí tienen código, el más parecido con el mismo tamaño en otra tienda
  (similitud de palabras, más reglas que descartan variantes como "hombre"/"mujer" o empaques distintos).
  Solo las coincidencias de confianza `high` se usan; las `review` quedan en `fct_match_review` para decidirlas
  a mano agregando una fila a `dbt/seeds/match_overrides.csv` (`confirmed` o `rejected`).
  `int_products__canonical_assignment` resuelve la prioridad: decisión manual, luego código, luego nombre.
- **Calidad.** dbt corre pruebas de unicidad, nulos y llaves foráneas, más pruebas propias
  (precios no negativos, forma de la clave de código de barras, aviso si la última descarga de una
  tienda no quedó `ok` y aviso si un mismo producto cuesta más de 3 veces entre tiendas).
- **Historial diario.** Turso guarda solo cambios, pero para graficar hace falta un precio por día. `int_prices__validity`
  calcula el rango de días en que estuvo vigente cada precio y `fct_daily_prices` lo cruza con el calendario
  `all_dates`. Un producto deja de aparecer el día en que se ve por última vez en el catálogo.
- **Índice de precios y canasta.** `int_prices__daily_best_per_store` deja un precio por día, producto canónico y
  tienda. `fct_store_price_index` compara cada tienda contra la mediana del mercado (100 = mediana, menos = más
  barata) con la media geométrica de los cocientes, solo con productos que venden 3 o más tiendas y sin atípicos;
  `is_reliable` marca las tiendas con al menos 100 productos comparados. `fct_basket_prices` suma el costo de las
  canastas del seed `basket_items` por tienda y día; solo las tiendas con la canasta completa reciben `cheapest_rank`.
- **Cobertura de descargas.** `fct_scrape_coverage` compara, por descarga y categoría, lo que reporta el sitio con lo
  descargado, para detectar categorías incompletas.
- **Seeds.** Datos de apoyo escritos a mano en CSV (`dbt/seeds/`): tipo de tienda (`dim_stores.store_type`), mapa de
  categorías unificadas, equivalencias de marca, decisiones manuales sobre el cruce de productos y las canastas.
