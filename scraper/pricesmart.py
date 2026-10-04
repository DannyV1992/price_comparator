"""Descarga el catálogo de PriceSmart Costa Rica (Bloomreach Discovery, público) a SQLite.

El sitio consulta a Bloomreach con una llave pública (`auth_key`) que envía a cualquier visitante;
`view_id=CR` da precios y existencias de todo el país, sin elegir club. Se usa curl_cffi porque
el sitio está detrás de Cloudflare.

El documento no trae la categoría del producto: se arma el árbol (200 nodos) y luego se consulta
cada categoría de nivel 2 para saber qué productos contiene. `price_CR` viene en centavos.
No hay código de barras, solo el SKU interno (`pid`).

Si la descarga empieza a fallar, la llave o los campos pueden haber cambiado: se vuelven a leer
en las llamadas a core.dxpapi.com que hace https://www.pricesmart.com/es-cr/ en el navegador.

Uso:
    python scraper/pricesmart.py --max-pages 1      # prueba pequeña
    python scraper/pricesmart.py                    # descarga completa (~100 peticiones)
"""
import argparse
import json
import random
import sys
import time
import zlib
from datetime import datetime, timezone

from curl_cffi import requests

from db import connect

STORE_NAME = "PriceSmart"
SITE = "https://www.pricesmart.com"
SHOP = SITE + "/es-cr"
API = "https://core.dxpapi.com/api/v1/core/"
AUTH = {"account_id": "7024", "auth_key": "ev7libhybjg5h1d1", "domain_key": "pricesmart_bloomreach_io_es",
        "view_id": "CR"}
FIELDS = ("pid,title,brand,slug,thumb_image,master_sku,price_CR,inventory_CR,saving_amount_CR,"
          "original_price_without_saving_CR,promoid_CR,sold_by_weight_CR,weight_CR,weight_uom_description_CR,"
          "uom_description_CR,variants")
ROWS = 200  # máximo que acepta Bloomreach
GAP_THRESHOLD = 0.95


class Client:
    def __init__(self, pause=(1.0, 2.0)):
        self.pause = pause
        self.retries = 0
        self.http = requests.Session(impersonate="chrome", timeout=40)

    def search(self, start=0, q="*", search_type="keyword", rows=ROWS):
        params = {**AUTH, "request_type": "search", "search_type": search_type, "q": q, "rows": rows,
                  "start": start, "fl": FIELDS, "url": SHOP, "request_id": 1,
                  "_br_uid_2": "uid=1:v=15.0:ts=1:hc=1"}
        for attempt in range(5):
            time.sleep(random.uniform(*self.pause))
            try:
                r = self.http.get(API, params=params)
            except requests.exceptions.RequestException as e:
                err = repr(e)
            else:
                if r.status_code == 200:
                    return r.json()
                if r.status_code not in (403, 429, 500, 502, 503, 504):
                    r.raise_for_status()
                err = f"HTTP {r.status_code}"
            wait = 5 * 2**attempt
            self.retries += 1
            print(f"  reintento en {wait}s ({err})", flush=True)
            time.sleep(wait)
        raise RuntimeError("Falló tras varios intentos")

    def all_docs(self, q="*", search_type="keyword", max_pages=None):
        """Recorre todas las páginas de una consulta. Devuelve (documentos, total, primera respuesta)."""
        docs, start, first = [], 0, None
        while True:
            j = self.search(start, q, search_type)
            first = first or j
            found = j["response"]["numFound"]
            docs += j["response"]["docs"]
            start += ROWS
            if start >= found or (max_pages and start // ROWS >= max_pages):
                return docs, found, first


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_store_id(conn):
    conn.execute("INSERT OR IGNORE INTO stores (name, website) VALUES (?, ?)", (STORE_NAME, SITE))
    return conn.execute("SELECT id FROM stores WHERE name = ?", (STORE_NAME,)).fetchone()["id"]


def save_categories(conn, store_id, nodes):
    for c in nodes:
        conn.execute(
            """INSERT INTO categories (store_id, store_category_id, name, parent_store_category_id, level)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(store_id, store_category_id) DO UPDATE SET
                 name = excluded.name, parent_store_category_id = excluded.parent_store_category_id,
                 level = excluded.level""",
            (store_id, c["cat_id"], c["cat_name"].strip(), c["parent"] or None, c["crumb"].count("/")),
        )


def save_product(conn, store_id, run_id, d, category, scraped_at):
    price = d["price_CR"] / 100  # viene en centavos
    original = d.get("original_price_without_saving_CR")  # este sí viene en colones
    raw_z = zlib.compress(json.dumps(d, ensure_ascii=False).encode("utf-8"))
    row = conn.execute(
        """INSERT INTO store_products
             (store_id, store_item_id, store_product_id, name, brand, ean, store_category_id,
              unit, unit_multiplier, url, image_url, raw_json_z, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, NULL, ?, ?, NULL, ?, ?, ?, ?, ?)
           ON CONFLICT(store_id, store_item_id) DO UPDATE SET
             name = excluded.name, brand = excluded.brand, ean = excluded.ean,
             store_category_id = excluded.store_category_id, unit = excluded.unit,
             unit_multiplier = excluded.unit_multiplier, url = excluded.url,
             image_url = excluded.image_url, raw_json_z = excluded.raw_json_z,
             last_seen = excluded.last_seen
           RETURNING id""",
        (
            store_id, d["pid"], d.get("master_sku") or d["pid"], d["title"].strip(),
            (d.get("brand") or "").strip() or None, category, d.get("uom_description_CR"),
            f"{SHOP}/producto/{d['slug']}/{d['pid']}" if d.get("slug") else None,
            d.get("thumb_image"), raw_z, scraped_at, scraped_at,
        ),
    ).fetchone()
    conn.execute(
        """INSERT INTO prices (store_product_id, run_id, scraped_at, price, list_price, available_qty)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (row["id"], run_id, scraped_at, price, float(original) if original else price,
         1 if d.get("inventory_CR") == "in stock" else 0),  # el sitio no publica la cantidad
    )


def run(max_pages=None):
    conn = connect()
    store_id = get_store_id(conn)
    client = Client()

    first = client.search(rows=1)
    total = first["response"]["numFound"]
    nodes = first["facet_counts"]["facet_fields"]["category"]
    save_categories(conn, store_id, nodes)
    conn.commit()
    print(f"El sitio reporta {total} productos y {len(nodes)} categorías", flush=True)

    # Categoría de cada producto: la de nivel 2 donde aparece (un producto puede estar en varias);
    # si no está en ninguna de nivel 2, la raíz.
    category_of = {}
    for level in (2, 1):
        todo = [n for n in nodes if n["crumb"].count("/") == level and n["count"] > 0]
        for n in (todo[:3] if max_pages else todo):
            docs, _, _ = client.all_docs(n["cat_id"], "category")
            for d in docs:
                category_of.setdefault(d["pid"], n["cat_id"])
        print(f"Productos con categoría tras el nivel {level}: {len(category_of)}", flush=True)

    run_id = conn.execute(
        "INSERT INTO scrape_runs (store_id, started_at, status) VALUES (?, ?, 'running')",
        (store_id, now()),
    ).lastrowid
    conn.commit()

    seen = set()
    status = "error"  # se queda así si el script se interrumpe
    try:
        start = 0
        while True:
            j = client.search(start)
            scraped_at = now()
            for d in j["response"]["docs"]:
                if d["pid"] not in seen:
                    seen.add(d["pid"])
                    save_product(conn, store_id, run_id, d, category_of.get(d["pid"]), scraped_at)
            conn.commit()
            start += ROWS
            print(f"  {min(start, total)}/{total} productos", flush=True)
            if start >= total or (max_pages and start // ROWS >= max_pages):
                break

        conn.execute(
            """INSERT OR REPLACE INTO scrape_run_categories
                 (run_id, category_path, name, reported_total, downloaded, retries)
               VALUES (?, 'all', 'Catálogo completo', ?, ?, ?)""",
            (run_id, total, len(seen), client.retries),
        )
        status = "ok" if (not max_pages and len(seen) >= GAP_THRESHOLD * total) else "partial"
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
    ap = argparse.ArgumentParser(description="Descarga el catálogo de PriceSmart Costa Rica")
    ap.add_argument("--max-pages", type=int, help="máximo de páginas de 200 (para pruebas)")
    args = ap.parse_args()
    run(args.max_pages)
