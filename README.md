# Comparador de precios

Comparador de precios de supermercado. **Web publicada: https://price-comparator-self.vercel.app/**

Tiendas descargadas hoy: **Más x Menos**, **Walmart** y **Maxi Pali** (VTEX), **Pequeño Mundo** (Magento GraphQL), **Automercado** (buscador Algolia) **Megasuper** y **Perimercados** (GraphQL de Instaleap) y **PriceSmart** (Bloomreach).

## Resumen del proyecto
**Plataforma de datos de precios de supermercados en Costa Rica (end-to-end).** Es un proyecto de ingeniería de datos de punta a punta, con una capa web encima.

- **Ingestión:** 8 scrapers de 5 tecnologías distintas (VTEX, Magento GraphQL, Algolia, Instaleap, Bloomreach), con reintentos, detección de huecos y evasión de Cloudflare con `curl_cffi`.
- **Orquestación y CI/CD:** GitHub Actions con matriz de tiendas, aviso por correo y reintento selectivo.
- **Almacenamiento:** Turso como capa operativa que guarda solo los cambios de precio, y un lakehouse en Databricks (Delta) con capas `raw`, `refined`, `intermediate` y `analytics`.
- **Transformación:** dbt con modelos, seeds y pruebas de calidad, y entity resolution (cruce de productos entre tiendas por EAN normalizado y por nombre y tamaño).
- **Serving:** una web en Next.js con búsqueda de texto completo (FTS5) y comparación de canasta, con sincronización incremental para mantenerse dentro del plan gratis.
- **Todo en costo cero**, y una decisión de arquitectura documentada en [docs/arquitectura.md](docs/arquitectura.md).

## Requisitos
- Python 3.12, `httpx` y `curl_cffi` (`pip install -r requirements.txt`). Pequeño Mundo y PriceSmart usan `curl_cffi` porque Cloudflare bloquea a `httpx` por su huella TLS.

## Uso
```
python scraper/vtex.py masxmenos --only-categories    # solo categorías
python scraper/vtex.py walmart --category 15 --max-pages 2  # prueba pequeña
python scraper/vtex.py masxmenos                       # descarga completa (~30 min)
python scraper/vtex.py walmart                         # Walmart completo (~1 h, 37.000 productos)
python scraper/vtex.py maxipali                        # Maxi Pali completo (~30 min, 19.000 productos)
python scraper/pequenomundo.py                         # Pequeño Mundo completo (~2 min)
python scraper/automercado.py                          # Automercado, sucursal 06 Moravia (~5 min)
python scraper/instaleap.py megasuper                  # Megasuper completo (~1 min)
python scraper/instaleap.py perimercados               # Perimercados (peridomicilio.com, ~1 min)
python scraper/pricesmart.py                           # PriceSmart completo (~5 min)
```
Al correr a mano, todo queda en `data/comparador.db` (no se sube a git) y cada ejecución agrega una fila de precio por producto. Ese SQLite es solo el paso intermedio: el historial real vive en Turso (ver abajo), porque en GitHub Actions cada descarga arranca con un SQLite temporal que se descarta al terminar.

Diferencias de Pequeño Mundo: no publica código de barras (`ean` queda vacío), la marca se saca de la descripción, no publica la cantidad en existencia (`available_qty` es 1 si hay y 0 si está agotado) y un agotado conserva su precio real (en Más x Menos aparece como 0).

Notas por tienda:
- **Automercado**: sin código de barras (hay un SKU interno). Los precios dependen de la sucursal; se usa la 06 (Moravia), la que muestra la web (`--branch` para otra). Unos 1.350 productos no tienen categoría en el sitio.
- **Megasuper**: el `sku` es el código de barras. Las promociones por cantidad (p. ej. 4 por 3.300) no cambian `price`; están en el JSON guardado. Sus códigos a veces llevan ceros a la izquierda que otras tiendas no tienen: al cruzar productos hay que normalizarlos (con eso coinciden ~4.300 con Más x Menos, y ~2.900 sin normalizar).
- **PriceSmart**: sin código de barras (SKU interno). Es un club con mucho producto que no es de súper (ropa, hogar). El precio viene en centavos y se convierte a colones; las existencias son solo hay / no hay. La categoría sale de consultar cada categoría de nivel 2 (y la raíz si no está en ninguna).
- **Fresh Market** se descartó: su sitio es un menú sin precios y vende por Uber Eats / PedidosYa.
- **Perimercados** vende en línea por `peridomicilio.com` (`perimercados.com` es un dominio estacionado). Misma plataforma que Megasuper, tienda 133. Su `sku` es interno; el `ean` es real en ~97% de los productos y un código corto de balanza en frutas y verduras (sirve normalizarlo con cuidado al cruzar: los códigos de menos de 8 dígitos no son códigos de barras).

## Automatización (Turso + GitHub Actions)
`.github/workflows/scrape.yml` descarga cada tienda a diario a las 09:17 (hora de Costa Rica), en un trabajo independiente por tienda, con un SQLite temporal, y lo sube a Turso con `sync/to_turso.py`. Esa sincronización se puede repetir sin duplicar datos. Cada trabajo termina en rojo si la descarga no queda en estado `ok`.

Secretos del repositorio (Settings → Secrets and variables → Actions): `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN`.

**En Turso, `prices` solo guarda cambios.** Se agrega una fila cuando el precio, el precio de lista o la disponibilidad (hay / no hay existencias) cambian respecto a la última fila del producto. La cantidad exacta no cuenta como cambio. Para saber el precio de un producto en una fecha, se toma su última fila hasta esa fecha; un precio `0` significa agotado en Más x Menos (en Pequeño Mundo, `available_qty = 0`). Que el producto siga en el catálogo lo dice `store_products.last_seen`, y cada descarga queda en `scrape_runs` (en `notes` se anota cuántos precios cambiaron). El SQLite local, en cambio, guarda una fila por producto en cada descarga.

Para subir a mano la última descarga local, define las mismas dos variables (o un archivo `.env` en la raíz, ignorado por git) y ejecuta:
```
python -m sync.to_turso
```

## Avisos por correo y repetir una sola tienda
- **Aviso.** Si algún trabajo falla (una tienda, la carga a Databricks o dbt), el último trabajo del flujo (`Avisar por correo`) manda un correo con los trabajos que fallaron, el paso exacto y los enlaces. Lo envía `ops/notify_failure.py` por SMTP. Secretos del repositorio: `SMTP_USER` (cuenta que envía, p. ej. Gmail), `SMTP_PASSWORD` (contraseña de aplicación de esa cuenta, no la normal) y `NOTIFY_EMAIL` (quién recibe; opcional, por defecto `SMTP_USER`).
- **Repetir lo que falló.** Si el error fue pasajero (red, 429, 5xx): en la corrida, botón **Re-run failed jobs**; repite solo los trabajos en rojo y conserva los que salieron bien.
- **Repetir una tienda con el código corregido.** Actions → Descarga diaria de precios → **Run workflow** → elegir la tienda en la lista (o «todas»). El botón de repetir usa el código del commit original; esta opción usa el actual. La lista de tiendas y sus tiempos máximos está en `.github/stores.json`; si se agrega una tienda, también hay que agregarla a las opciones de `scrape.yml`.

## Databricks (lakehouse)
Después de que terminan todas las tiendas, un trabajo final (`Cargar a Databricks`) copia Turso al catálogo `supermarket_prices`, esquema `raw`, en tablas Delta (`stores`, `categories`, `scrape_runs`, `scrape_run_categories`, `store_products`, `prices`) con `sync/to_databricks.py`. Los datos llegan tal como están en Turso (ids de Turso, fechas como texto, sin el JSON original); `refined` y `analytics` se construyen a partir de `raw`. Es un trabajo aparte: si falla, las descargas de las tiendas no se ven afectadas, pero el flujo sale en rojo y avisa por correo. Se puede repetir sin duplicar: `prices` continúa desde el mayor id que ya hay y las demás tablas se mezclan con `MERGE`.

Secretos adicionales: `DATABRICKS_HOST`, `DATABRICKS_HTTP_PATH` y `DATABRICKS_TOKEN`. Para correrlo a mano, las mismas tres variables (más las de Turso) en `.env`:
```
pip install -r requirements-databricks.txt
python -m sync.to_databricks
```

Capas (una por esquema): `raw` (como llegan), `refined` (staging de dbt: limpio y tipado, EAN normalizado), `intermediate` (transformaciones previas a los marts) y `analytics` (marts de dbt: `dim_` y `fct_`, para BI). El diagrama y las decisiones están en [docs/arquitectura.md](docs/arquitectura.md).

### dbt
`dbt/` sigue la convención de dbt: `models/staging/turso` (`stg_turso__*`, vistas en `refined`), `models/intermediate` (`int_*`, vistas en `intermediate`) y `models/marts` (`dim_stores`, `dim_products`, `dim_canonical_products`, `fct_price_changes`, `fct_current_prices`, `fct_daily_prices`, `fct_price_comparison`, `fct_scrape_runs`, `fct_scrape_coverage`, `fct_match_review`, `fct_store_price_index`, `fct_basket_prices`, `web_products`, `web_offers`, tablas en `analytics`). `models/utilities` tiene el calendario (`all_dates`) y `seeds/` los datos de apoyo escritos a mano en CSV (`store_info`, `basket_items`, `category_mapping`, `brand_aliases`, `match_overrides`; los tres últimos están vacíos). Los productos sin código de barras se cruzan por nombre y tamaño; los casos dudosos salen en `fct_match_review` y se resuelven agregando una fila a `match_overrides.csv` (`confirmed` o `rejected`). Incluye la macro `normalize_ean` y las pruebas de calidad. En el flujo diario corre como último trabajo, después de la carga a Databricks. A mano, con las variables de Databricks en el entorno:
```
pip install -r dbt/requirements.txt
dbt build --project-dir dbt --profiles-dir dbt
```

## Web (`web/`)
Publicada en [price-comparator-self.vercel.app](https://price-comparator-self.vercel.app/). Página para armar una lista de compras y compararla entre supermercados (Next.js). Tiene búsqueda sin distinguir tildes, una tabla con el precio de cada producto en cada tienda (verde el más barato, rojo el más caro) y el total por supermercado. Si una tienda no tiene un producto, se elige un reemplazo con su cantidad; en PriceSmart, que solo vende paquetes, el total suma la parte equivalente y se muestra aparte lo que costarían los paquetes enteros. Cada producto enlaza a su página en la tienda, y la lista, los reemplazos y la configuración se guardan en el navegador (y se pueden exportar a un archivo). La web no lee de Databricks: lee un SQLite que se genera a partir de los marts `web_products` y `web_offers` (que incluyen los productos sin cruzar, como una tienda sola; sin ellos Automercado casi no aparecería).
```
python -m sync.to_web          # escribe data/web.db desde Databricks (necesita las variables de Databricks)
cd web
npm install
npm run dev                    # http://localhost:3000
```
Para publicarla, `WEB_DATABASE_URL` y `WEB_AUTH_TOKEN` (token de solo lectura) apuntan a una base de Turso aparte de la de las descargas. Esa base la mantiene el último trabajo del flujo diario (`Publicar datos de la web`): corre `sync.to_web` y luego `python -m sync.web_to_turso`, que compara `data/web.db` con lo que hay en Turso y escribe solo las filas nuevas, cambiadas o borradas (así se cuidan las escrituras del plan gratis). Secretos del repositorio: `WEB_DATABASE_URL` y `WEB_WRITE_TOKEN` (token con escritura). A mano, con esas dos variables en `.env`: `python -m sync.web_to_turso`.

## Tablas
- `stores`: tiendas
- `categories`: árbol de categorías de cada tienda
- `store_products`: un SKU por fila (nombre, marca, EAN, unidad, JSON original comprimido con zlib)
- `prices`: historial de precios (precio, precio de lista, disponibilidad, fecha)
- `scrape_runs`: registro de cada descarga (queda `partial` si alguna categoría baja menos del 95% de lo esperado)
- `scrape_run_categories`: por descarga y categoría, lo que reporta el sitio, lo descargado y los reintentos

## Leer el JSON original de un producto
```python
import sqlite3, zlib, json
row = sqlite3.connect("data/comparador.db").execute("SELECT raw_json_z FROM store_products LIMIT 1").fetchone()
print(json.loads(zlib.decompress(row[0])))
```

## Notas
- Pausa de 1 a 2 s entre peticiones; reintenta con espera si el sitio responde 429/5xx.
- VTEX limita cada búsqueda a 2.550 resultados, por eso las categorías grandes se recorren por subcategoría.
- Revisa los términos de uso de la tienda antes de publicar un servicio basado en estos datos.
