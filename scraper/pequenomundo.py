"""Descarga el catálogo de Pequeño Mundo (Magento, GraphQL público) a SQLite.

Cloudflare bloquea a httpx por la huella TLS, por eso se usa curl_cffi (imita a Chrome).
No se pide `custom_attributesV2`: ahí la tienda expone su costo de compra, que no es un
precio de venta y no nos corresponde guardar.

Uso:
    python scraper/pequenomundo.py --only-categories    # solo el árbol de categorías
    python scraper/pequenomundo.py --max-pages 2        # prueba pequeña
    python scraper/pequenomundo.py                      # descarga completa (~33 peticiones)
"""
import argparse
import json
import random
import re
import sys
import time
import zlib
from datetime import datetime, timezone

from curl_cffi import requests

from db import connect

STORE_NAME = "Pequeño Mundo"
SITE = "https://tienda.pequenomundo.com"
GRAPHQL = SITE + "/graphql"
PAGE_SIZE = 100
GAP_THRESHOLD = 0.95  # bajo este porcentaje de lo esperado, la descarga se marca incompleta

CATEGORY_FIELDS = "uid name level"
CATEGORIES_QUERY = "{categories{items{" + "".join(
    f"{CATEGORY_FIELDS} children{{" for _ in range(5)) + CATEGORY_FIELDS + "}" * 5 + "}}}"

PRODUCTS_QUERY = """query($page: Int!, $size: Int!) {
  products(search: "", pageSize: $size, currentPage: $page, sort: {name: ASC}) {
    total_count
    page_info { total_pages }
    items {
      uid sku name url_key stock_status only_x_left_in_stock
      image { url }
      categories { uid name level url_path }
      description { html }
      price_range { minimum_price {
        regular_price { value currency }
        final_price { value }
        discount { amount_off percent_off }
      } }
    }
  }
}"""


class Client:
    def __init__(self, pause=(1.0, 2.0)):
        self.pause = pause
        self.retries = 0
        self.http = requests.Session(impersonate="chrome", timeout=40)

    def query(self, query, variables=None):
        for attempt in range(5):
            time.sleep(random.uniform(*self.pause))
            try:
                r = self.http.post(GRAPHQL, json={"query": query, "variables": variables or {}})
            except requests.exceptions.RequestException as e:
                err = repr(e)
            else:
                data = r.json() if r.status_code == 200 else None
                if data and data.get("data"):
                    return data["data"]
                err = f"HTTP {r.status_code}" if data is None else f"respuesta sin datos: {str(data.get('errors'))[:200]}"
            wait = 5 * 2**attempt
            self.retries += 1
            print(f"  reintento en {wait}s ({err})", flush=True)
            time.sleep(wait)
        raise RuntimeError("Falló tras varios intentos")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_store_id(conn):
    conn.execute("INSERT OR IGNORE INTO stores (name, website) VALUES (?, ?)", (STORE_NAME, SITE))
    return conn.execute("SELECT id FROM stores WHERE name = ?", (STORE_NAME,)).fetchone()["id"]


def save_categories(conn, store_id, nodes, parent=None, level=1):
    for n in nodes:
        conn.execute(
            """INSERT INTO categories (store_id, store_category_id, name, parent_store_category_id, level)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(store_id, store_category_id) DO UPDATE SET
                 name = excluded.name,
                 parent_store_category_id = excluded.parent_store_category_id,
                 level = excluded.level""",
            (store_id, n["uid"], n["name"].strip(), parent, level),
        )
        save_categories(conn, store_id, n.get("children") or [], n["uid"], level + 1)


NO_BRAND = {"", "n/a", "genérico", "generico"}  # relleno que la tienda pone cuando no hay marca


def brand_of(description):
    """La marca viene en la descripción: 'Marca: X' o el segundo campo de 'nombre~marca~tamaño'."""
    m = re.search(r"Marca:\s*([^|]+)", description)
    head = description.split("||", 1)[0].split("~")
    brand = m.group(1).strip() if m else (head[1].strip() if len(head) == 3 else "")
    return None if brand.lower() in NO_BRAND else brand


def save_product_categories(conn, store_id, cats):
    """Agrega las categorías del producto que no salen en el árbol (p. ej. las ocultas del menú)."""
    by_path = {c["url_path"]: c["uid"] for c in cats}
    for c in cats:
        parent = by_path.get(c["url_path"].rpartition("/")[0])
        conn.execute(
            """INSERT OR IGNORE INTO categories (store_id, store_category_id, name, parent_store_category_id, level)
               VALUES (?, ?, ?, ?, ?)""",
            (store_id, c["uid"], c["name"].strip(), parent, c["level"] - 1),  # Magento cuenta la raíz técnica
        )


def save_product(conn, store_id, run_id, p, scraped_at):
    """Guarda un producto (un SKU por fila) y su precio actual."""
    description = (p.get("description") or {}).get("html") or ""
    cats = p.get("categories") or []
    save_product_categories(conn, store_id, cats)
    deepest = max(cats, key=lambda c: c["level"], default=None)  # a igualdad, la primera listada
    price = p["price_range"]["minimum_price"]
    in_stock = p["stock_status"] == "IN_STOCK"
    qty = (p.get("only_x_left_in_stock") or 1) if in_stock else 0  # la tienda no publica la cantidad

    raw_z = zlib.compress(json.dumps(p, ensure_ascii=False).encode("utf-8"))
    row = conn.execute(
        """INSERT INTO store_products
             (store_id, store_item_id, store_product_id, name, brand, ean, store_category_id,
              unit, unit_multiplier, url, image_url, raw_json_z, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, NULL, ?, ?, ?, ?, ?)
           ON CONFLICT(store_id, store_item_id) DO UPDATE SET
             name = excluded.name, brand = excluded.brand, ean = excluded.ean,
             store_category_id = excluded.store_category_id, unit = excluded.unit,
             unit_multiplier = excluded.unit_multiplier, url = excluded.url,
             image_url = excluded.image_url, raw_json_z = excluded.raw_json_z,
             last_seen = excluded.last_seen
           RETURNING id""",
        (
            store_id, p["sku"], p["uid"], p["name"].strip(), brand_of(description),
            deepest["uid"] if deepest else None,
            f"{SITE}/{p['url_key']}.html" if p.get("url_key") else None,
            (p.get("image") or {}).get("url"), raw_z, scraped_at, scraped_at,
        ),
    ).fetchone()
    conn.execute(
        """INSERT INTO prices (store_product_id, run_id, scraped_at, price, list_price, available_qty)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (row["id"], run_id, scraped_at, price["final_price"]["value"], price["regular_price"]["value"], qty),
    )


def run(max_pages=None, only_categories=False):
    conn = connect()
    store_id = get_store_id(conn)
    client = Client()

    roots = client.query(CATEGORIES_QUERY)["categories"]["items"]
    for default in roots:  # "Default Category" es solo la raíz técnica de Magento
        save_categories(conn, store_id, default.get("children") or [])
    conn.commit()
    n_cat = conn.execute("SELECT COUNT(*) FROM categories WHERE store_id = ?", (store_id,)).fetchone()[0]
    print(f"Categorías guardadas: {n_cat}", flush=True)
    if only_categories:
        return

    run_id = conn.execute(
        "INSERT INTO scrape_runs (store_id, started_at, status) VALUES (?, ?, 'running')",
        (store_id, now()),
    ).lastrowid
    conn.commit()

    seen = set()
    total = 0
    status = "error"  # se queda así si el script se interrumpe
    try:
        page = 1
        while True:
            data = client.query(PRODUCTS_QUERY, {"page": page, "size": PAGE_SIZE})["products"]
            total = data["total_count"]
            scraped_at = now()
            for p in data["items"]:
                if p["sku"] not in seen:
                    seen.add(p["sku"])
                    save_product(conn, store_id, run_id, p, scraped_at)
            conn.commit()
            print(f"  página {page}/{data['page_info']['total_pages']}: {len(seen)} productos", flush=True)
            if page >= data["page_info"]["total_pages"] or (max_pages and page >= max_pages):
                break
            page += 1

        conn.execute(
            """INSERT OR REPLACE INTO scrape_run_categories
                 (run_id, category_path, name, reported_total, downloaded, retries)
               VALUES (?, 'all', 'Catálogo completo', ?, ?, ?)""",
            (run_id, total, len(seen), client.retries),
        )
        complete = len(seen) >= GAP_THRESHOLD * total
        status = "ok" if (complete and not max_pages) else "partial"
    finally:
        notes = None
        if status != "error":
            notes = f"el sitio reporta {total} productos"
            if not max_pages and status == "partial":
                notes += f"; descarga incompleta ({len(seen)}/{total})"
        conn.execute(
            "UPDATE scrape_runs SET finished_at = ?, status = ?, products_seen = ?, items_seen = ?, notes = ? WHERE id = ?",
            (now(), status, len(seen), len(seen), notes, run_id),
        )
        conn.commit()
    print(f"Listo. Estado: {status} | productos: {len(seen)} (el sitio reporta {total})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Descarga el catálogo de Pequeño Mundo")
    ap.add_argument("--only-categories", action="store_true", help="solo guarda el árbol de categorías")
    ap.add_argument("--max-pages", type=int, help="máximo de páginas de 100 (para pruebas)")
    args = ap.parse_args()
    run(args.max_pages, args.only_categories)
