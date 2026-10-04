# comparador-super

Comparador de precios de supermercado. Tiendas descargadas hoy: **Más x Menos**, **Walmart** y **Maxi Pali** (VTEX), **Pequeño Mundo** (Magento GraphQL), **Automercado** (buscador Algolia) **Megasuper** y **Perimercados** (GraphQL de Instaleap) y **PriceSmart** (Bloomreach).

## Requisitos
- Python 3.12, `httpx` y `curl_cffi` (`pip install -r requirements.txt`). Pequeño Mundo usa `curl_cffi` porque Cloudflare bloquea a `httpx` por su huella TLS.

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
Todo queda en `data/comparador.db` (no se sube a git). Cada ejecución agrega un precio nuevo por producto, así se arma el historial.

Diferencias de Pequeño Mundo: no publica código de barras (`ean` queda vacío), la marca se saca de la descripción, no publica la cantidad en existencia (`available_qty` es 1 si hay y 0 si está agotado) y un agotado conserva su precio real (en Más x Menos aparece como 0).

Notas por tienda:
- **Automercado**: sin código de barras (hay un SKU interno). Los precios dependen de la sucursal; se usa la 06 (Moravia), la que muestra la web (`--branch` para otra). Unos 1.350 productos no tienen categoría en el sitio.
- **Megasuper**: el `sku` es el código de barras. Las promociones por cantidad (p. ej. 4 por 3.300) no cambian `price`; están en el JSON guardado. Sus códigos a veces llevan ceros a la izquierda que otras tiendas no tienen: al cruzar productos hay que normalizarlos (con eso coinciden ~4.300 con Más x Menos, y ~2.900 sin normalizar).
- **PriceSmart**: sin código de barras (SKU interno). Es un club con mucho producto que no es de súper (ropa, hogar). El precio viene en centavos y se convierte a colones; las existencias son solo hay / no hay. La categoría sale de consultar cada categoría de nivel 2 (y la raíz si no está en ninguna).
- **Fresh Market** se descartó: su sitio es un menú sin precios y vende por Uber Eats / PedidosYa.
- **Perimercados** vende en línea por `peridomicilio.com` (`perimercados.com` es un dominio estacionado). Misma plataforma que Megasuper, tienda 133. Su `sku` es interno; el `ean` es real en ~97% de los productos y un código corto de balanza en frutas y verduras (sirve normalizarlo con cuidado al cruzar: los códigos de menos de 8 dígitos no son códigos de barras).

## Automatización (Turso + GitHub Actions)
`.github/workflows/scrape.yml` descarga cada tienda a diario a las 03:00 (hora de Costa Rica), en un trabajo independiente por tienda, con un SQLite temporal, y lo sube a Turso con `scraper/sync_turso.py`. Esa sincronización se puede repetir sin duplicar datos. Cada trabajo termina en rojo si la descarga no queda en estado `ok`.

Secretos del repositorio (Settings → Secrets and variables → Actions): `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN`.

**En Turso, `prices` solo guarda cambios.** Se agrega una fila cuando el precio, el precio de lista o la disponibilidad (hay / no hay existencias) cambian respecto a la última fila del producto. La cantidad exacta no cuenta como cambio. Para saber el precio de un producto en una fecha, se toma su última fila hasta esa fecha; un precio `0` significa agotado en Más x Menos (en Pequeño Mundo, `available_qty = 0`). Que el producto siga en el catálogo lo dice `store_products.last_seen`, y cada descarga queda en `scrape_runs` (en `notes` se anota cuántos precios cambiaron). El SQLite local, en cambio, guarda una fila por producto en cada descarga.

Para subir a mano la última descarga local, define las mismas dos variables (o un archivo `.env` en la raíz, ignorado por git) y ejecuta:
```
python scraper/sync_turso.py
```

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
