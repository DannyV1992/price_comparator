# comparador-super

Comparador de precios de supermercado. Etapa actual: descargar el catálogo de **Más x Menos** a una base SQLite local.

## Requisitos
- Python 3.12 y `httpx` (`pip install -r requirements.txt`)

## Uso
```
python scraper/masxmenos.py --only-categories          # solo categorías
python scraper/masxmenos.py --category 15 --max-pages 2 # prueba pequeña
python scraper/masxmenos.py                            # descarga completa (~10-15 min)
```
Todo queda en `data/comparador.db` (no se sube a git). Cada ejecución agrega un precio nuevo por producto, así se arma el historial.

## Automatización (Turso + GitHub Actions)
`.github/workflows/scrape.yml` descarga el catálogo cada día a las 03:00 (hora de Costa Rica) en un SQLite temporal y lo sube a Turso con `scraper/sync_turso.py`. Esa sincronización se puede repetir sin duplicar datos. El flujo termina en rojo si la descarga no queda en estado `ok`.

Secretos del repositorio (Settings → Secrets and variables → Actions): `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN`.

**En Turso, `prices` solo guarda cambios.** Se agrega una fila cuando el precio, el precio de lista o la disponibilidad (hay / no hay existencias) cambian respecto a la última fila del producto. La cantidad exacta no cuenta como cambio. Para saber el precio de un producto en una fecha, se toma su última fila hasta esa fecha; un precio `0` significa agotado. Que el producto siga en el catálogo lo dice `store_products.last_seen`, y cada descarga queda en `scrape_runs` (en `notes` se anota cuántos precios cambiaron). El SQLite local, en cambio, guarda una fila por producto en cada descarga.

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
