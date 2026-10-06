"""Sube a una base de Turso el SQLite de la web (data/web.db, que escribe `python -m sync.to_web`).

Es una sincronización incremental: lee lo que ya hay en Turso, lo compara con el archivo local y escribe solo
las filas nuevas, cambiadas o que ya no existen. Así cada día se escriben unas pocas filas y no las 180.000
(el plan gratis de Turso limita las escrituras por mes). La primera vez carga todo. Se puede repetir sin duplicar.

Variables de entorno (o un archivo .env en la raíz del proyecto):
    WEB_DATABASE_URL     p. ej. libsql://comparador-web-mi-org.turso.io
    WEB_WRITE_TOKEN      token con permiso de escritura (la web usa otro, de solo lectura, en WEB_AUTH_TOKEN)

Uso:
    python -m sync.web_to_turso
    python -m sync.web_to_turso --src otra/ruta.db
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

from sync.common import Turso, load_env
from sync.to_web import DEFAULT_OUT, OFFER_COLS, SCHEMA

PAGE = 20000   # filas por página al leer lo que ya hay en Turso
BATCH = 400    # sentencias por transacción al escribir

PRODUCT_DB_COLS = ["product_id", "name", "brand", "image_url", "category_name", "n_stores"]
# Columnas de offers en la base de la web (to_web.py las llama igual, salvo product_name -> name)
OFFER_DB_COLS = OFFER_COLS


def ensure_schema(remote):
    exists = remote.execute("SELECT 1 FROM sqlite_master WHERE name = 'products'")
    if exists:
        return
    print("Creando las tablas en Turso ...", flush=True)
    statements = [s.strip() for s in SCHEMA.split(";") if s.strip()]
    remote.batch([(s, ()) for s in statements])


def read_remote(remote, table, cols, key):
    """Devuelve {clave: (rowid, fila)} con todo lo que hay en Turso, leyendo por páginas de rowid."""
    rows, last = {}, 0
    while True:
        page = remote.execute(
            f"SELECT rowid, {', '.join(cols)} FROM {table} WHERE rowid > ? ORDER BY rowid LIMIT {PAGE}", (last,))
        if not page:
            return rows
        for rowid, *values in page:
            rows[values[key]] = (rowid, tuple(values))
        last = page[-1][0]


def read_local(db, table, cols, key):
    return {r[key]: tuple(r) for r in db.execute(f"SELECT {', '.join(cols)} FROM {table}")}


def same(a, b):
    """Igual, ignorando la diferencia entre 10 y 10.0 que introduce el ida y vuelta por JSON."""
    return all(x == y for x, y in zip(a, b))


def flush(remote, stmts, force=False):
    """Escribe en bloques; cada bloque es una transacción."""
    while len(stmts) >= BATCH or (force and stmts):
        remote.batch(stmts[:BATCH])
        del stmts[:BATCH]


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Sube data/web.db a la base de Turso de la web (incremental)")
    ap.add_argument("--src", type=Path, default=DEFAULT_OUT, help="SQLite de origen (por defecto data/web.db)")
    args = ap.parse_args()

    missing = [k for k in ("WEB_DATABASE_URL", "WEB_WRITE_TOKEN") if not os.environ.get(k)]
    if missing:
        sys.exit(f"Faltan variables de entorno: {', '.join(missing)}")
    if not args.src.exists():
        sys.exit(f"No existe {args.src}. Genérelo primero con: python -m sync.to_web")

    remote = Turso(os.environ["WEB_DATABASE_URL"], os.environ["WEB_WRITE_TOKEN"])
    local = sqlite3.connect(args.src)
    ensure_schema(remote)

    print("Leyendo lo que ya hay en Turso ...", flush=True)
    old_products = read_remote(remote, "products", PRODUCT_DB_COLS, 0)
    old_offers = read_remote(remote, "offers", OFFER_DB_COLS, 0)
    new_products = read_local(local, "products", PRODUCT_DB_COLS, 0)
    new_offers = read_local(local, "offers", OFFER_DB_COLS, 0)

    stmts = []
    p_cols, o_cols = ", ".join(PRODUCT_DB_COLS), ", ".join(OFFER_DB_COLS)
    p_marks, o_marks = ", ".join("?" * len(PRODUCT_DB_COLS)), ", ".join("?" * len(OFFER_DB_COLS))
    counts = dict(offers_new=0, offers_changed=0, offers_gone=0, products_new=0, products_changed=0, products_gone=0)

    # 1) Precios que ya no existen (antes que los productos)
    for key in old_offers:
        if key not in new_offers:
            stmts.append(("DELETE FROM offers WHERE offer_key = ?", (key,)))
            counts["offers_gone"] += 1
    flush(remote, stmts)

    # 2) Productos que ya no existen (se saca también del índice de búsqueda)
    for key, (rowid, row) in old_products.items():
        if key not in new_products:
            stmts.append(("INSERT INTO products_fts(products_fts, rowid, name, brand) VALUES ('delete', ?, ?, ?)",
                          (rowid, row[1], row[2])))
            stmts.append(("DELETE FROM products WHERE product_id = ?", (key,)))
            counts["products_gone"] += 1
    flush(remote, stmts)

    # 3) Productos nuevos y cambiados
    for key, row in new_products.items():
        if key not in old_products:
            stmts.append((f"INSERT INTO products ({p_cols}) VALUES ({p_marks})", row))
            stmts.append(("INSERT INTO products_fts(rowid, name, brand) "
                          "SELECT rowid, name, brand FROM products WHERE product_id = ?", (key,)))
            counts["products_new"] += 1
        else:
            rowid, old = old_products[key]
            if same(old, row):
                continue
            if (old[1], old[2]) != (row[1], row[2]):  # cambió el nombre o la marca: rehacer su entrada de búsqueda
                stmts.append(("INSERT INTO products_fts(products_fts, rowid, name, brand) VALUES ('delete', ?, ?, ?)",
                              (rowid, old[1], old[2])))
                stmts.append(("INSERT INTO products_fts(rowid, name, brand) VALUES (?, ?, ?)", (rowid, row[1], row[2])))
            sets = ", ".join(f"{c} = ?" for c in PRODUCT_DB_COLS[1:])
            stmts.append((f"UPDATE products SET {sets} WHERE product_id = ?", (*row[1:], key)))
            counts["products_changed"] += 1
    flush(remote, stmts)

    # 4) Precios nuevos y cambiados
    for key, row in new_offers.items():
        if key not in old_offers:
            stmts.append((f"INSERT INTO offers ({o_cols}) VALUES ({o_marks})", row))
            counts["offers_new"] += 1
        elif not same(old_offers[key][1], row):
            sets = ", ".join(f"{c} = ?" for c in OFFER_DB_COLS[1:])
            stmts.append((f"UPDATE offers SET {sets} WHERE offer_key = ?", (*row[1:], key)))
            counts["offers_changed"] += 1
    flush(remote, stmts)

    exported = local.execute("SELECT value FROM meta WHERE key = 'exported_at'").fetchone()
    if exported:
        stmts.append(("INSERT OR REPLACE INTO meta(key, value) VALUES ('exported_at', ?)", (exported[0],)))
    flush(remote, stmts, force=True)

    print("Listo. " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"En Turso ahora: {len(new_products)} productos, {len(new_offers)} precios")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
