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
