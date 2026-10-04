"""Sube a Turso la última descarga guardada en el SQLite local.

El scraper escribe en un SQLite local (rápido). Este script copia esa descarga a la base
de Turso en lotes, para conservar el historial fuera de la máquina que corrió el scraper.
En Turso solo se agrega una fila a `prices` cuando el precio, el precio de lista o la
disponibilidad cambian respecto a la última fila del producto; así la tabla no se llena de
repeticiones. Los datos del producto y `last_seen` se actualizan en cada descarga.
Se puede repetir sin duplicar datos: si una sincronización se corta, basta volver a lanzarla.

Variables de entorno (o un archivo .env en la raíz del proyecto):
    TURSO_DATABASE_URL   p. ej. libsql://mi-base-mi-org.turso.io
    TURSO_AUTH_TOKEN     token de la base

Uso:
    python -m sync.to_turso                      # sincroniza la última descarga
    python -m sync.to_turso --run-id 2           # una descarga concreta
    python -m sync.to_turso --fail-unless-ok     # sale con error si la descarga no quedó 'ok'
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

from scraper.db import DB_PATH, SCHEMA
from sync.common import Turso, load_env

BATCH_ROWS = 100  # productos (con su precio) por petición


def split_statements(script):
    """Separa un script SQL en sentencias sueltas."""
    out, buf = [], ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    return out


UPSERT_PRODUCT = """INSERT INTO store_products
      (store_id, store_item_id, store_product_id, name, brand, ean, store_category_id,
       unit, unit_multiplier, url, image_url, raw_json_z, first_seen, last_seen)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(store_id, store_item_id) DO UPDATE SET
      name = excluded.name, brand = excluded.brand, ean = excluded.ean,
      store_category_id = excluded.store_category_id, unit = excluded.unit,
      unit_multiplier = excluded.unit_multiplier, url = excluded.url,
      image_url = excluded.image_url, raw_json_z = excluded.raw_json_z,
      last_seen = excluded.last_seen"""

# No repite el precio si el lote se reenvía: una fila por producto y descarga.
INSERT_PRICE = """INSERT INTO prices (store_product_id, run_id, scraped_at, price, list_price, available_qty)
    SELECT sp.id, ?, ?, ?, ?, ? FROM store_products sp
    WHERE sp.store_id = ? AND sp.store_item_id = ?
      AND NOT EXISTS (SELECT 1 FROM prices x WHERE x.store_product_id = sp.id AND x.run_id = ?)"""

# Último precio guardado de cada producto de la tienda.
LATEST_PRICES = """SELECT sp.store_item_id, p.price, p.list_price, p.available_qty
    FROM store_products sp JOIN prices p ON p.store_product_id = sp.id
    WHERE sp.store_id = ? AND p.id = (SELECT MAX(id) FROM prices WHERE store_product_id = sp.id)"""


def price_state(price, list_price, qty):
    """Lo que cuenta como un cambio: precio, precio de lista y si hay o no existencias.

    La cantidad exacta no cuenta: cambia a cada rato y llenaría la tabla de filas repetidas.
    """
    return (price, list_price, qty is not None and qty > 0)


def latest_prices(remote, store_id):
    return {r[0]: price_state(r[1], r[2], r[3]) for r in remote.execute(LATEST_PRICES, (store_id,))}


def sync(remote, local, run_id):
    local.executescript(SCHEMA)  # bases creadas con una versión anterior del esquema
    run = local.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
    if run is None:
        sys.exit(f"No existe la descarga {run_id} en la base local")
    if run["status"] == "running":
        sys.exit(f"La descarga {run_id} sigue en estado 'running'; espera a que termine")
    store = local.execute("SELECT name, website FROM stores WHERE id = ?", (run["store_id"],)).fetchone()

    print("Preparando esquema en Turso ...", flush=True)
    for stmt in split_statements(SCHEMA):
        remote.execute(stmt)

    remote.execute("INSERT OR IGNORE INTO stores (name, website) VALUES (?, ?)", (store["name"], store["website"]))
    store_id = remote.execute("SELECT id FROM stores WHERE name = ?", (store["name"],))[0][0]

    # La descarga se identifica por tienda + hora de inicio, porque los ids locales no sirven en la nube.
    found = remote.execute("SELECT id, status FROM scrape_runs WHERE store_id = ? AND started_at = ?",
                           (store_id, run["started_at"]))
    if found and found[0][1] != "syncing":
        print(f"La descarga {run['started_at']} ya estaba sincronizada (id {found[0][0]}, estado {found[0][1]}).")
        return run["status"]
    if not found:
        remote.execute("INSERT INTO scrape_runs (store_id, started_at, status) VALUES (?, ?, 'syncing')",
                       (store_id, run["started_at"]))
        found = remote.execute("SELECT id, status FROM scrape_runs WHERE store_id = ? AND started_at = ?",
                               (store_id, run["started_at"]))
    remote_run = found[0][0]

    cats = local.execute("SELECT store_category_id, name, parent_store_category_id, level FROM categories "
                         "WHERE store_id = ?", (run["store_id"],)).fetchall()
    for i in range(0, len(cats), 500):
        remote.batch([
            ("""INSERT INTO categories (store_id, store_category_id, name, parent_store_category_id, level)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(store_id, store_category_id) DO UPDATE SET
                  name = excluded.name, parent_store_category_id = excluded.parent_store_category_id,
                  level = excluded.level""",
             (store_id, c["store_category_id"], c["name"], c["parent_store_category_id"], c["level"]))
            for c in cats[i:i + 500]
        ])
    print(f"Categorías sincronizadas: {len(cats)}", flush=True)

    total = local.execute("SELECT COUNT(*) FROM prices WHERE run_id = ?", (run_id,)).fetchone()[0]
    rows = local.execute(
        """SELECT sp.store_item_id, sp.store_product_id, sp.name, sp.brand, sp.ean, sp.store_category_id,
                  sp.unit, sp.unit_multiplier, sp.url, sp.image_url, sp.raw_json_z, sp.first_seen,
                  sp.last_seen, p.scraped_at, p.price, p.list_price, p.available_qty
           FROM prices p JOIN store_products sp ON sp.id = p.store_product_id
           WHERE p.run_id = ? ORDER BY p.id""", (run_id,))
    latest = latest_prices(remote, store_id)
    print(f"Productos con precio en Turso: {len(latest)}", flush=True)
    expected = {}  # estado de precio que debe quedar en Turso al terminar
    done = 0
    while True:
        chunk = rows.fetchmany(BATCH_ROWS)
        if not chunk:
            break
        stmts = []
        for r in chunk:
            stmts.append((UPSERT_PRODUCT, (store_id, *r[0:13])))  # mantiene al día datos y last_seen
            state = expected[r[0]] = price_state(r[14], r[15], r[16])
            if latest.get(r[0]) != state:
                stmts.append((INSERT_PRICE, (remote_run, r[13], r[14], r[15], r[16], store_id, r[0], remote_run)))
        remote.batch(stmts)
        done += len(chunk)
        if done % (BATCH_ROWS * 10) == 0 or done == total:
            print(f"  {done}/{total} productos procesados", flush=True)

    run_cats = local.execute("SELECT category_path, name, reported_total, downloaded, retries "
                             "FROM scrape_run_categories WHERE run_id = ?", (run_id,)).fetchall()
    remote.batch([
        ("""INSERT OR REPLACE INTO scrape_run_categories
              (run_id, category_path, name, reported_total, downloaded, retries) VALUES (?, ?, ?, ?, ?, ?)""",
         (remote_run, *c))
        for c in run_cats
    ])

    after = latest_prices(remote, store_id)
    bad = sum(1 for item, state in expected.items() if after.get(item) != state)
    if bad:
        sys.exit(f"Faltan datos en Turso: {bad} productos sin el precio esperado. Vuelve a lanzar la sincronización.")
    changed = remote.execute("SELECT COUNT(*) FROM prices WHERE run_id = ?", (remote_run,))[0][0]
    notes = "; ".join(filter(None, [run["notes"], f"precios nuevos o modificados: {changed}"]))
    remote.execute(
        "UPDATE scrape_runs SET finished_at = ?, status = ?, products_seen = ?, items_seen = ?, notes = ? WHERE id = ?",
        (run["finished_at"], run["status"], run["products_seen"], run["items_seen"], notes, remote_run),
    )
    print(f"Listo. Descarga {run['started_at']} sincronizada como id {remote_run}: "
          f"{total} productos, {changed} con precio nuevo o modificado.")
    return run["status"]


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Sincroniza la última descarga local con Turso")
    ap.add_argument("--db", type=Path, default=DB_PATH, help="SQLite local (por defecto data/comparador.db)")
    ap.add_argument("--run-id", type=int, help="id de la descarga local (por defecto, la última)")
    ap.add_argument("--fail-unless-ok", action="store_true", help="sale con error si la descarga no quedó 'ok'")
    args = ap.parse_args()

    url, token = os.environ.get("TURSO_DATABASE_URL"), os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        sys.exit("Faltan TURSO_DATABASE_URL y TURSO_AUTH_TOKEN (variables de entorno o archivo .env)")

    local = sqlite3.connect(args.db)
    local.row_factory = sqlite3.Row
    run_id = args.run_id or local.execute("SELECT MAX(id) FROM scrape_runs").fetchone()[0]
    if run_id is None:
        sys.exit("La base local no tiene ninguna descarga")

    status = sync(Turso(url, token), local, run_id)
    if args.fail_unless_ok and status != "ok":
        sys.exit(f"La descarga terminó con estado '{status}', no 'ok'; revisa scrape_runs.notes")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
