"""Descarga el catálogo de Más x Menos (API pública de VTEX) a SQLite.

Uso:
    python scraper/masxmenos.py --only-categories       # solo el árbol de categorías
    python scraper/masxmenos.py --category 15 --max-pages 2   # prueba pequeña
    python scraper/masxmenos.py                         # descarga completa
"""
import argparse
import json
import random
import re
import sys
import time
import zlib
from datetime import datetime, timezone

import httpx

from db import connect

STORE_NAME = "Más x Menos"
SITE = "https://www.masxmenos.cr"
API = SITE + "/api/catalog_system/pub"
PAGE_SIZE = 50
MAX_FROM = 2500  # VTEX responde 400 si _from > 2500


class Client:
    def __init__(self, pause=(1.0, 2.0)):
        self.pause = pause
        self.http = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (compatible; comparador-super/0.1; uso personal)"},
            timeout=40,
            follow_redirects=True,
        )

    def get(self, url, params=None):
        for attempt in range(5):
            time.sleep(random.uniform(*self.pause))
            try:
                r = self.http.get(url, params=params)
            except httpx.TransportError as e:
                err = repr(e)
            else:
                if r.status_code in (200, 206):
                    return r
                if r.status_code not in (429, 500, 502, 503, 504):
                    r.raise_for_status()
                err = f"HTTP {r.status_code}"
            wait = 5 * 2**attempt
            print(f"  reintento en {wait}s ({err})", flush=True)
            time.sleep(wait)
        raise RuntimeError(f"Falló tras varios intentos: {url}")

    def tree(self):
        return self.get(f"{API}/category/tree/4").json()

    def search(self, category_path, start):
        """Devuelve (productos, total) para una categoría, p. ej. '11/123'."""
        params = {"_from": start, "_to": start + PAGE_SIZE - 1}
        if category_path:
            params["fq"] = f"C:/{category_path}/"
        r = self.get(f"{API}/products/search", params)
        m = re.search(r"/(\d+)$", r.headers.get("resources", ""))
        total = int(m.group(1)) if m else 0
        return (r.json() if r.content else []), total


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
            (store_id, str(n["id"]), n["name"], parent, level),
        )
        save_categories(conn, store_id, n.get("children", []), str(n["id"]), level + 1)


def pick_offer(item):
    sellers = item.get("sellers") or []
    seller = next((s for s in sellers if s.get("sellerDefault")), sellers[0] if sellers else None)
    return (seller or {}).get("commertialOffer") or {}


def save_product(conn, store_id, run_id, product, scraped_at, seen_items):
    """Guarda un producto de VTEX (una fila por item/SKU) y su precio actual."""
    items = product.get("items") or []
    raw_z = zlib.compress(json.dumps(product, ensure_ascii=False).encode("utf-8"))
    saved = 0
    for item in items:
        item_id = str(item["itemId"])
        if item_id in seen_items:
            continue
        seen_items.add(item_id)

        images = item.get("images") or []
        name = product["productName"] if len(items) == 1 else (item.get("nameComplete") or product["productName"])
        row = conn.execute(
            """INSERT INTO store_products
                 (store_id, store_item_id, store_product_id, name, brand, ean, store_category_id,
                  unit, unit_multiplier, url, image_url, raw_json_z, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(store_id, store_item_id) DO UPDATE SET
                 name = excluded.name, brand = excluded.brand, ean = excluded.ean,
                 store_category_id = excluded.store_category_id, unit = excluded.unit,
                 unit_multiplier = excluded.unit_multiplier, url = excluded.url,
                 image_url = excluded.image_url, raw_json_z = excluded.raw_json_z,
                 last_seen = excluded.last_seen
               RETURNING id""",
            (
                store_id, item_id, str(product["productId"]), name, product.get("brand"),
                item.get("ean") or None, str(product.get("categoryId") or "") or None,
                item.get("measurementUnit"), item.get("unitMultiplier"),
                product.get("link"), images[0].get("imageUrl") if images else None,
                raw_z, scraped_at, scraped_at,
            ),
        ).fetchone()

        offer = pick_offer(item)
        conn.execute(
            """INSERT INTO prices (store_product_id, run_id, scraped_at, price, list_price, available_qty)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row["id"], run_id, scraped_at, offer.get("Price"), offer.get("ListPrice"),
             offer.get("AvailableQuantity")),
        )
        saved += 1
    return saved


def walk(client, node, parent_path, handle, max_pages):
    """Recorre una categoría paginando. Si excede el límite de VTEX, baja a sus hijas."""
    path = f"{parent_path}/{node['id']}" if parent_path else str(node["id"])
    page, total = client.search(path, 0)
    if not total:
        return
    print(f"  [{path}] {node['name']}: {total} productos", flush=True)
    handle(page)
    start, pages = PAGE_SIZE, 1
    while start < total and start <= MAX_FROM and not (max_pages and pages >= max_pages):
        page, _ = client.search(path, start)
        if not page:
            break
        handle(page)
        start += PAGE_SIZE
        pages += 1
    if total > MAX_FROM + PAGE_SIZE and not max_pages:
        for child in node.get("children", []):
            walk(client, child, path, handle, max_pages)


def run(category=None, max_pages=None, only_categories=False):
    conn = connect()
    store_id = get_store_id(conn)
    client = Client()

    tree = client.tree()
    save_categories(conn, store_id, tree)
    conn.commit()
    n_cat = conn.execute("SELECT COUNT(*) FROM categories WHERE store_id = ?", (store_id,)).fetchone()[0]
    print(f"Categorías guardadas: {n_cat} ({len(tree)} raíz)", flush=True)
    if only_categories:
        return

    roots = [n for n in tree if category is None or str(n["id"]) == str(category)]
    if not roots:
        sys.exit(f"No existe la categoría raíz {category}")

    started = now()
    run_id = conn.execute(
        "INSERT INTO scrape_runs (store_id, started_at, status) VALUES (?, ?, 'running')",
        (store_id, started),
    ).lastrowid
    conn.commit()

    seen_items, seen_products = set(), set()
    status = "error"  # se queda así si el script se interrumpe

    def handle(products):
        scraped_at = now()
        for p in products:
            seen_products.add(str(p["productId"]))
            save_product(conn, store_id, run_id, p, scraped_at, seen_items)
        conn.commit()

    try:
        for root in roots:
            print(f"== {root['name']}", flush=True)
            walk(client, root, None, handle, max_pages)
        status = "partial" if (category or max_pages) else "ok"
    finally:
        notes = None
        if status == "ok":
            _, site_total = client.search(None, 0)
            notes = f"el sitio reporta {site_total} productos"
            print(f"Productos únicos descargados: {len(seen_products)} (el sitio reporta {site_total})")
        conn.execute(
            "UPDATE scrape_runs SET finished_at = ?, status = ?, products_seen = ?, items_seen = ?, notes = ? WHERE id = ?",
            (now(), status, len(seen_products), len(seen_items), notes, run_id),
        )
        conn.commit()
    print(f"Listo. Estado: {status} | productos: {len(seen_products)} | items: {len(seen_items)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Descarga el catálogo de Más x Menos")
    ap.add_argument("--only-categories", action="store_true", help="solo guarda el árbol de categorías")
    ap.add_argument("--category", help="id de una categoría raíz (descarga parcial)")
    ap.add_argument("--max-pages", type=int, help="máximo de páginas de 50 por categoría (para pruebas)")
    args = ap.parse_args()
    run(args.category, args.max_pages, args.only_categories)
