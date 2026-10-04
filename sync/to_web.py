"""Exporta de Databricks a un SQLite los datos que lee la web (marts web_products y web_offers).

La web no lee de Databricks: el warehouse tarda en arrancar, cobra por uso y su token no puede llegar al
navegador. En su lugar lee este SQLite, que trae la búsqueda por texto (FTS5, sin distinguir tildes).
El archivo se escribe aparte y se reemplaza al final, así la web nunca ve una copia a medias.

Variables de entorno (o un archivo .env en la raíz del proyecto):
    DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN

Uso:
    python -m sync.to_web                       # escribe data/web.db
    python -m sync.to_web --out otra/ruta.db
"""
import argparse
import os
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from databricks import sql

from sync.common import load_env

CATALOG = "supermarket_prices"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "web.db"
BATCH = 5000

SCHEMA = """
CREATE TABLE products (
    product_id    TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    brand         TEXT,
    image_url     TEXT,
    category_name TEXT,
    n_stores      INTEGER NOT NULL
);

CREATE VIRTUAL TABLE products_fts USING fts5(
    name, brand, content='products', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE offers (
    offer_key          TEXT PRIMARY KEY,
    product_id         TEXT NOT NULL REFERENCES products(product_id),
    store_id           INTEGER NOT NULL,
    store_name         TEXT NOT NULL,
    store_product_id   INTEGER NOT NULL,
    store_product_name TEXT,
    url                TEXT,
    price              REAL,
    list_price         REAL,
    discount_pct       REAL,
    is_available       INTEGER NOT NULL,
    price_since        TEXT,
    is_price_outlier   INTEGER NOT NULL
);
CREATE INDEX idx_offers_product ON offers(product_id);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

PRODUCT_COLS = ["product_id", "product_name", "brand", "image_url", "category_name", "n_stores"]
OFFER_COLS = ["offer_key", "product_id", "store_id", "store_name", "store_product_id", "store_product_name",
              "url", "price", "list_price", "discount_pct", "is_available", "price_since", "is_price_outlier"]


def plain(value):
    """Valor de Databricks -> valor que entiende SQLite."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def copy_table(cur, db, source, cols, target):
    cur.execute(f"SELECT {', '.join(cols)} FROM {CATALOG}.analytics.{source}")
    insert = f"INSERT INTO {target} VALUES ({', '.join('?' * len(cols))})"
    total = 0
    while True:
        rows = cur.fetchmany(BATCH)
        if not rows:
            return total
        db.executemany(insert, [[plain(v) for v in r] for r in rows])
        total += len(rows)


def main():
    load_env()
    ap = argparse.ArgumentParser(description="Exporta los marts de la web a un SQLite")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="archivo de salida (por defecto data/web.db)")
    args = ap.parse_args()

    need = ["DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit(f"Faltan variables de entorno: {', '.join(missing)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)

    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://").rstrip("/"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    ) as conn:
        cur = conn.cursor()
        print("Exportando web_products ...", flush=True)
        n_products = copy_table(cur, db, "web_products", PRODUCT_COLS, "products")
        print(f"  {n_products} productos", flush=True)
        print("Exportando web_offers ...", flush=True)
        n_offers = copy_table(cur, db, "web_offers", OFFER_COLS, "offers")
        print(f"  {n_offers} precios", flush=True)

    db.execute("INSERT INTO products_fts(rowid, name, brand) SELECT rowid, name, brand FROM products")
    db.execute("INSERT INTO meta VALUES ('exported_at', ?)", (datetime.now().astimezone().isoformat(timespec="seconds"),))
    db.commit()
    db.close()
    tmp.replace(args.out)
    print(f"Listo: {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
