"""Base de datos SQLite del comparador: esquema y conexión."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "comparador.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    website TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    store_id                 INTEGER NOT NULL REFERENCES stores(id),
    store_category_id        TEXT NOT NULL,
    name                     TEXT NOT NULL,
    parent_store_category_id TEXT,
    level                    INTEGER NOT NULL,
    PRIMARY KEY (store_id, store_category_id)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id            INTEGER PRIMARY KEY,
    store_id      INTEGER NOT NULL REFERENCES stores(id),
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    status        TEXT NOT NULL,          -- running | ok | partial | error
    products_seen INTEGER DEFAULT 0,
    items_seen    INTEGER DEFAULT 0,
    notes         TEXT
);

-- Una fila por categoría recorrida en cada descarga: sirve para detectar huecos.
CREATE TABLE IF NOT EXISTS scrape_run_categories (
    run_id         INTEGER NOT NULL REFERENCES scrape_runs(id),
    category_path  TEXT NOT NULL,         -- ruta de ids, p. ej. 6/40
    name           TEXT NOT NULL,
    reported_total INTEGER NOT NULL,      -- productos que dice tener el sitio
    downloaded     INTEGER NOT NULL,      -- productos que bajamos
    retries        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, category_path)
);

-- Una fila por SKU (item) tal como aparece en la tienda.
CREATE TABLE IF NOT EXISTS store_products (
    id                INTEGER PRIMARY KEY,
    store_id          INTEGER NOT NULL REFERENCES stores(id),
    store_item_id     TEXT NOT NULL,      -- itemId de VTEX
    store_product_id  TEXT NOT NULL,      -- productId de VTEX
    name              TEXT NOT NULL,
    brand             TEXT,
    ean               TEXT,               -- código de barras
    store_category_id TEXT,               -- categoría más específica
    unit              TEXT,
    unit_multiplier   REAL,
    url               TEXT,
    image_url         TEXT,
    raw_json_z        BLOB,               -- JSON original del producto, comprimido con zlib
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    UNIQUE (store_id, store_item_id)
);
CREATE INDEX IF NOT EXISTS idx_store_products_ean ON store_products(ean);

-- Historial: cada descarga agrega filas, nunca modifica las anteriores.
CREATE TABLE IF NOT EXISTS prices (
    id               INTEGER PRIMARY KEY,
    store_product_id INTEGER NOT NULL REFERENCES store_products(id),
    run_id           INTEGER NOT NULL REFERENCES scrape_runs(id),
    scraped_at       TEXT NOT NULL,
    price            REAL,
    list_price       REAL,
    available_qty    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_prices_product ON prices(store_product_id, scraped_at);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
