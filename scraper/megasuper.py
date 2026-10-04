"""Descarga el catálogo de Megasuper (API GraphQL de Instaleap que usa el sitio) a SQLite.

El sitio es una tienda Instaleap; su API es pública para cualquier visitante y responde con un
certificado válido, así que no hace falta tocar el TLS de www.megasuper.com. Se usa la tienda de
comercio electrónico M102, la que fija el sitio.

El `sku` es el código de barras (EAN). `price` es el precio por unidad con IVA (por kilo en
productos por peso). Las promociones (p. ej. 4 por 3.300) no cambian `price`: quedan en el JSON
original guardado.

Uso:
    python scraper/megasuper.py --category 16        # una categoría raíz (prueba pequeña)
    python scraper/megasuper.py                      # descarga completa (~25 peticiones)
"""
import argparse
import json
import random
import sys
import time
import zlib
from datetime import datetime, timezone

import httpx

from db import connect

STORE_NAME = "Megasuper"
SITE = "https://www.megasuper.com"
API = "https://nextgentheadless.instaleap.io/api/v3"
HEADERS = {  # las que envía el sitio a cualquier visitante
    "content-type": "application/json",
    "dpl-api-key": "09e9a997-5c41-4460-8fe7-3fa37f9774f1",
    "client-name": "e-commerce Moira Engine MEGASUPER",
}
BASE = {"clientId": "MEGASUPER", "storeReference": "M102"}
PAGE_SIZE = 1000
GAP_THRESHOLD = 0.95

TREE_QUERY = """query($i: GetCategoryInput!) {
  getCategory(getCategoryInput: $i) { name reference }
}"""

PRODUCTS_QUERY = """query($i: GetProductsByCategoryInput!) {
  getProductsByCategory(getProductsByCategoryInput: $i) {
    pagination { page pages total { value } }
    category { products {
      name sku ean brand price previousPrice unit subUnit subQty photosUrl slug isActive isAvailable
      stock maxQty priceBeforeTaxes taxTotal
      promotion { type isActive description startDateTime endDateTime
                  conditions { quantity price priceBeforeTaxes taxTotal } }
      promotions { type description promotionReference startDateTime endDateTime isActive
                   benefit { type label value values qty } }
      categoriesData { name reference path categoryNamesPath level }
    } }
  }
}"""


class Client:
    def __init__(self, pause=(1.0, 2.0)):
        self.pause = pause
        self.retries = 0
        self.http = httpx.Client(headers=HEADERS, timeout=90)

    def query(self, query, variables):
        for attempt in range(5):
            time.sleep(random.uniform(*self.pause))
            try:
                r = self.http.post(API, json={"query": query, "variables": variables})
            except httpx.TransportError as e:
                err = repr(e)
            else:
                data = r.json() if r.status_code == 200 else None
                if data and data.get("data"):
                    return data["data"]
                if r.status_code not in (200, 429, 500, 502, 503, 504):
                    r.raise_for_status()
                err = f"HTTP {r.status_code}" if data is None else f"respuesta sin datos: {str(data.get('errors'))[:200]}"
            wait = 5 * 2**attempt
            self.retries += 1
            print(f"  reintento en {wait}s ({err})", flush=True)
            time.sleep(wait)
        raise RuntimeError("Falló tras varios intentos")

    def products(self, category, page):
        """Devuelve (productos, total de la categoría, páginas)."""
        d = self.query(PRODUCTS_QUERY, {"i": {**BASE, "categoryReference": category,
                                               "currentPage": page, "pageSize": PAGE_SIZE}})["getProductsByCategory"]
        return (d["category"]["products"] or []), d["pagination"]["total"]["value"], d["pagination"]["pages"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_store_id(conn):
    conn.execute("INSERT OR IGNORE INTO stores (name, website) VALUES (?, ?)", (STORE_NAME, SITE))
    return conn.execute("SELECT id FROM stores WHERE name = ?", (STORE_NAME,)).fetchone()["id"]


def save_categories(conn, store_id, categories):
    """Guarda las categorías de un producto; el padre sale de la ruta '/16/16001/1600102'."""
    for c in categories:
        parts = c["path"].strip("/").split("/")
        parent = parts[-2] if len(parts) > 1 else None
        conn.execute(
            """INSERT INTO categories (store_id, store_category_id, name, parent_store_category_id, level)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(store_id, store_category_id) DO UPDATE SET
                 name = excluded.name, parent_store_category_id = excluded.parent_store_category_id,
                 level = excluded.level""",
            (store_id, c["reference"], c["name"].strip(), parent, c["level"]),
        )


def save_product(conn, store_id, run_id, p, scraped_at):
    cats = p.get("categoriesData") or []
    save_categories(conn, store_id, cats)
    deepest = max(cats, key=lambda c: c["level"], default=None)
    ean = (p.get("ean") or [None])[0]
    photos = p.get("photosUrl") or []
    raw_z = zlib.compress(json.dumps(p, ensure_ascii=False).encode("utf-8"))
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
            store_id, p["sku"], p["sku"], p["name"].strip(), (p.get("brand") or "").strip() or None, ean,
            deepest["reference"] if deepest else None, p.get("unit"), p.get("subQty"),
            f"{SITE}/p/{p['slug']}" if p.get("slug") else None, photos[0] if photos else None,
            raw_z, scraped_at, scraped_at,
        ),
    ).fetchone()
    in_stock = bool(p.get("isAvailable")) and (p.get("stock") or 0) > 0
    conn.execute(
        """INSERT INTO prices (store_product_id, run_id, scraped_at, price, list_price, available_qty)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (row["id"], run_id, scraped_at, p["price"], p.get("previousPrice") or p["price"],
         p.get("stock") if in_stock else 0),
    )


def run(category=None):
    conn = connect()
    store_id = get_store_id(conn)
    client = Client()

    roots = client.query(TREE_QUERY, {"i": BASE})["getCategory"]
    if category:
        roots = [r for r in roots if r["reference"] == category]
        if not roots:
            sys.exit(f"No existe la categoría raíz {category}")
    print(f"Categorías raíz: {len(roots)}", flush=True)

    run_id = conn.execute(
        "INSERT INTO scrape_runs (store_id, started_at, status) VALUES (?, ?, 'running')",
        (store_id, now()),
    ).lastrowid
    conn.commit()

    seen = set()
    reported = 0
    gaps = []
    status = "error"  # se queda así si el script se interrumpe
    try:
        for root in roots:
            retries_before = client.retries
            before = len(seen)
            page, pages, total = 1, 1, 0
            while page <= pages:
                products, total, pages = client.products(root["reference"], page)
                scraped_at = now()
                for p in products:
                    if p["sku"] not in seen:
                        seen.add(p["sku"])
                        save_product(conn, store_id, run_id, p, scraped_at)
                conn.commit()
                page += 1
            got = len(seen) - before
            reported += total
            conn.execute(
                """INSERT OR REPLACE INTO scrape_run_categories
                     (run_id, category_path, name, reported_total, downloaded, retries)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, root["reference"], root["name"], total, got, client.retries - retries_before),
            )
            conn.commit()
            print(f"  [{root['reference']}] {root['name']}: {got}/{total} productos", flush=True)
            if got < GAP_THRESHOLD * total:
                gaps.append(f"{root['reference']} {root['name']} ({got}/{total})")
                print(f"  AVISO: [{root['reference']}] {root['name']} bajó {got} de {total}", flush=True)
        status = "partial" if (category or gaps) else "ok"
    finally:
        notes = None
        if status != "error":
            notes = f"el sitio reporta {reported} productos"
            if gaps:
                notes += "; categorías incompletas: " + ", ".join(gaps)
        conn.execute(
            "UPDATE scrape_runs SET finished_at = ?, status = ?, products_seen = ?, items_seen = ?, notes = ? WHERE id = ?",
            (now(), status, len(seen), len(seen), notes, run_id),
        )
        conn.commit()
    print(f"Listo. Estado: {status} | productos: {len(seen)} (el sitio reporta {reported})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Descarga el catálogo de Megasuper")
    ap.add_argument("--category", help="referencia de una categoría raíz, p. ej. 16 (descarga parcial)")
    args = ap.parse_args()
    run(args.category)
