"""Descarga el catálogo de Automercado (buscador Algolia público del sitio) a SQLite.

El sitio busca productos en Algolia a través de un proxy, con una llave de solo búsqueda que
el navegador envía a cualquier visitante. Algolia devuelve como máximo 1.000 resultados por
consulta, así que el catálogo se parte por rangos de precio hasta que cada rango tenga <= 1.000.
Los precios dependen de la sucursal; por defecto se usa la 06 (Moravia), la que muestra la web.

Si la descarga empieza a fallar con 403/404, la llave o el proxy pueden haber cambiado: se
vuelven a leer en la llamada "queries" que hace https://automercado.cr/buscar en el navegador.

Uso:
    python scraper/automercado.py --max-pages 1      # prueba pequeña
    python scraper/automercado.py                    # descarga completa
    python scraper/automercado.py --branch 10        # otra sucursal (crea otra tienda en la base)
"""
import argparse
import json
import random
import re
import sys
import time
import unicodedata
import zlib
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from db import connect

SITE = "https://automercado.cr"
SEARCH_URL = "https://auto-mercado-prod.topsort.workers.dev/1/indexes/*/queries"
SEARCH_KEY = {"x-algolia-api-key": "335287091ff4a66858e0ad021ca45b76", "x-algolia-application-id": "FU5XFX7KNL"}
INDEX = "Product_CatalogueV2"
DEFAULT_BRANCH = "06"
MAX_HITS = 1000  # tope de Algolia por consulta
MAX_AMOUNT = 2**22  # cota superior de precio para la bisección (~4,2 millones de colones)
MIN_RANGE = 0.01  # un rango más angosto que esto ya no se parte
GAP_THRESHOLD = 0.95
BRANCH_NAMES = {"06": "Moravia"}


def attributes(branch):
    return ["ecomDescription", "marca", "productPresentation", "originatingCountry", "hierarchicalCategories",
            "categoryPageId", "imageUrl", "productNumber", "objectID", "hasDiscount", "marcaPrivada",
            "variableWeight", "isNewProduct", f"storeDetail.{branch}"]


class Client:
    def __init__(self, branch, pause=(1.0, 2.0)):
        self.branch = branch
        self.pause = pause
        self.retries = 0
        self.http = httpx.Client(timeout=60)

    def search(self, lo=None, hi=None, hits=0, page=0):
        """Devuelve el resultado de Algolia para el rango de precio [lo, hi) de la sucursal."""
        b = self.branch
        numeric = ([f"storeDetail.{b}.amount>={lo}"] if lo is not None else []) + \
                  ([f"storeDetail.{b}.amount<{hi}"] if hi is not None else [])
        params = {"query": "", "hitsPerPage": hits, "page": page,
                  "facetFilters": json.dumps([[f"storeDetail.{b}.storeid:{b}"]]),
                  "attributesToHighlight": "[]", "attributesToSnippet": "[]"}
        if numeric:
            params["numericFilters"] = json.dumps(numeric)
        if hits:
            params["attributesToRetrieve"] = json.dumps(attributes(b))
        body = json.dumps({"requests": [{"indexName": INDEX, "params": urlencode(params)}]})
        for attempt in range(5):
            time.sleep(random.uniform(*self.pause))
            try:
                r = self.http.post(SEARCH_URL, params=SEARCH_KEY, content=body,
                                   headers={"content-type": "application/x-www-form-urlencoded"})
            except httpx.TransportError as e:
                err = repr(e)
            else:
                if r.status_code == 200:
                    return r.json()["results"][0]
                if r.status_code not in (429, 500, 502, 503, 504):
                    r.raise_for_status()
                err = f"HTTP {r.status_code}"
            wait = 5 * 2**attempt
            self.retries += 1
            print(f"  reintento en {wait}s ({err})", flush=True)
            time.sleep(wait)
        raise RuntimeError("Falló tras varios intentos")

    def ranges(self, lo=0.0, hi=float(MAX_AMOUNT), known=None):
        """Parte el rango de precio por la mitad hasta que cada trozo tenga <= 1.000 productos.

        Devuelve tuplas (lo, hi, cantidad).
        """
        count = self.search(lo, hi)["nbHits"] if known is None else known
        if count == 0:
            return
        if count <= MAX_HITS or hi - lo <= MIN_RANGE:
            yield lo, hi, count
            return
        mid = (lo + hi) / 2
        yield from self.ranges(lo, mid)
        yield from self.ranges(mid, hi)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_store_id(conn, name):
    conn.execute("INSERT OR IGNORE INTO stores (name, website) VALUES (?, ?)", (name, SITE))
    return conn.execute("SELECT id FROM stores WHERE name = ?", (name,)).fetchone()["id"]


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def save_category_path(conn, store_id, path):
    """Las categorías llegan como texto 'A > B > C': ese texto es su id."""
    parts = path.split(" > ")
    for i in range(len(parts)):
        here = " > ".join(parts[: i + 1])
        parent = " > ".join(parts[:i]) or None
        conn.execute(
            """INSERT OR IGNORE INTO categories (store_id, store_category_id, name, parent_store_category_id, level)
               VALUES (?, ?, ?, ?, ?)""",
            (store_id, here, parts[i], parent, i + 1),
        )


def save_product(conn, store_id, run_id, hit, branch, scraped_at):
    detail = (hit.get("storeDetail") or {}).get(branch) or {}
    cats = hit.get("hierarchicalCategories") or {}
    category = cats.get("lvl2") or cats.get("lvl1") or cats.get("lvl0")
    if category:
        save_category_path(conn, store_id, category)
    name = hit["ecomDescription"].strip()
    raw_z = zlib.compress(json.dumps(hit, ensure_ascii=False).encode("utf-8"))
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
            store_id, hit["productNumber"], hit["objectID"], name, (hit.get("marca") or "").strip() or None,
            category, hit.get("productPresentation"),
            f"{SITE}/p/{slug(name)}/id/{hit['objectID']}", hit.get("imageUrl"), raw_z, scraped_at, scraped_at,
        ),
    ).fetchone()
    in_stock = detail.get("hasInvontory") == 1 and detail.get("productAvailable") is not False
    conn.execute(
        """INSERT INTO prices (store_product_id, run_id, scraped_at, price, list_price, available_qty)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (row["id"], run_id, scraped_at, detail.get("amount"), detail.get("basePrice"), 1 if in_stock else 0),
    )


def run(branch=DEFAULT_BRANCH, max_pages=None):
    label = BRANCH_NAMES.get(branch)
    # Con la sucursal por defecto la tienda se llama "Automercado"; otra sucursal es otra tienda.
    name = "Automercado" if branch == DEFAULT_BRANCH else f"Automercado (sucursal {label or branch})"
    conn = connect()
    store_id = get_store_id(conn, name)
    client = Client(branch)

    total = client.search()["nbHits"]
    if not total:
        sys.exit(f"La sucursal {branch} no devolvió productos")
    print(f"Sucursal {branch}: el sitio reporta {total} productos", flush=True)

    run_id = conn.execute(
        "INSERT INTO scrape_runs (store_id, started_at, status) VALUES (?, ?, 'running')",
        (store_id, now()),
    ).lastrowid
    conn.commit()

    seen = set()
    status = "error"  # se queda así si el script se interrumpe
    try:
        pages = 0
        for lo, hi, count in client.ranges():
            if count > MAX_HITS:
                print(f"  AVISO: {count} productos con precio entre {lo} y {hi}; solo se bajan {MAX_HITS}", flush=True)
            page = 0
            while page * MAX_HITS < min(count, MAX_HITS):
                hits = client.search(lo, hi, hits=MAX_HITS, page=page)["hits"]
                scraped_at = now()
                for h in hits:
                    if h["productNumber"] not in seen:
                        seen.add(h["productNumber"])
                        save_product(conn, store_id, run_id, h, branch, scraped_at)
                conn.commit()
                page += 1
                pages += 1
            print(f"  precio [{lo:g}, {hi:g}): {count} productos | acumulado {len(seen)}", flush=True)
            if max_pages and pages >= max_pages:
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
            notes = f"el sitio reporta {total} productos (sucursal {branch})"
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
    ap = argparse.ArgumentParser(description="Descarga el catálogo de Automercado")
    ap.add_argument("--branch", default=DEFAULT_BRANCH, help="id de sucursal (por defecto 06, Moravia)")
    ap.add_argument("--max-pages", type=int, help="máximo de páginas de datos (para pruebas)")
    args = ap.parse_args()
    run(args.branch, args.max_pages)
