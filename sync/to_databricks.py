"""Copia Turso a Databricks (esquema `raw` de Unity Catalog, tablas Delta).

Turso tiene las ocho tiendas juntas, así que la carga sale de ahí y no de cada descarga: un solo
proceso escribe en Delta y no hay escrituras simultáneas sobre las mismas tablas.
Los datos llegan tal como están en Turso (ids de Turso, fechas como texto); la limpieza y el
tipado son trabajo de la capa `refined`. No se copia el JSON original de cada producto.

Cada tabla se baja de Turso a un archivo JSON Lines, se sube a un Volume y se mezcla con MERGE,
por lo que se puede repetir sin duplicar datos. `prices` es solo de agregar: se continúa desde
el mayor id que ya hay en Delta. Las demás se actualizan completas (son chicas).

Variables de entorno (o un archivo .env en la raíz del proyecto), además de las de Turso:
    DATABRICKS_HOST        p. ej. dbc-xxxx.cloud.databricks.com
    DATABRICKS_HTTP_PATH   p. ej. /sql/1.0/warehouses/xxxx
    DATABRICKS_TOKEN       token personal

Uso:
    python -m sync.to_databricks
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from databricks import sql

from sync.common import Turso, load_env

CATALOG = "supermarket_prices"
SCHEMA = "raw"
VOLUME = "landing"
PAGE = 20000  # filas por archivo

# key: columnas de la llave; paged: se baja por tramos de id (el id debe ser la primera columna);
# incremental: solo filas con id mayor al máximo que ya hay en Delta (tabla de solo agregar).
TABLES = {
    "stores": dict(
        key=["id"], paged=True,
        cols=[("id", "BIGINT"), ("name", "STRING"), ("website", "STRING")],
        select="SELECT id, name, website FROM stores"),
    "categories": dict(
        key=["store_id", "store_category_id"],
        cols=[("store_id", "BIGINT"), ("store_category_id", "STRING"), ("name", "STRING"),
              ("parent_store_category_id", "STRING"), ("level", "INT")],
        select="SELECT store_id, store_category_id, name, parent_store_category_id, level FROM categories"),
    "scrape_runs": dict(
        key=["id"], paged=True,
        cols=[("id", "BIGINT"), ("store_id", "BIGINT"), ("started_at", "STRING"), ("finished_at", "STRING"),
              ("status", "STRING"), ("products_seen", "INT"), ("items_seen", "INT"), ("notes", "STRING")],
        select="SELECT id, store_id, started_at, finished_at, status, products_seen, items_seen, notes "
               "FROM scrape_runs"),
    "scrape_run_categories": dict(
        key=["run_id", "category_path"],
        cols=[("run_id", "BIGINT"), ("category_path", "STRING"), ("name", "STRING"),
              ("reported_total", "INT"), ("downloaded", "INT"), ("retries", "INT")],
        select="SELECT run_id, category_path, name, reported_total, downloaded, retries "
               "FROM scrape_run_categories"),
    "store_products": dict(
        key=["id"], paged=True,
        cols=[("id", "BIGINT"), ("store_id", "BIGINT"), ("store_item_id", "STRING"),
              ("store_product_id", "STRING"), ("name", "STRING"), ("brand", "STRING"), ("ean", "STRING"),
              ("store_category_id", "STRING"), ("unit", "STRING"), ("unit_multiplier", "DOUBLE"),
              ("url", "STRING"), ("image_url", "STRING"), ("first_seen", "STRING"), ("last_seen", "STRING")],
        select="SELECT id, store_id, store_item_id, store_product_id, name, brand, ean, store_category_id, "
               "unit, unit_multiplier, url, image_url, first_seen, last_seen FROM store_products"),
    "prices": dict(
        key=["id"], paged=True, incremental=True,
        cols=[("id", "BIGINT"), ("store_product_id", "BIGINT"), ("run_id", "BIGINT"), ("scraped_at", "STRING"),
              ("price", "DOUBLE"), ("list_price", "DOUBLE"), ("available_qty", "INT")],
        select="SELECT id, store_product_id, run_id, scraped_at, price, list_price, available_qty FROM prices"),
}


def pages(remote, spec, after=0):
    """Genera las filas de Turso en tramos."""
    if not spec.get("paged"):
        yield remote.execute(spec["select"])
        return
    while True:
        rows = remote.execute(f"{spec['select']} WHERE id > ? ORDER BY id LIMIT {PAGE}", (after,))
        if not rows:
            return
        yield rows
        after = rows[-1][0]


def ddl(table, spec):
    cols = ", ".join(f"{n} {t}" for n, t in spec["cols"])
    return f"CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.{table} ({cols}, _loaded_at TIMESTAMP)"


def merge(table, spec, path):
    names = [n for n, _ in spec["cols"]]
    schema = ", ".join(f"{n} {t}" for n, t in spec["cols"])
    on = " AND ".join(f"t.{k} = s.{k}" for k in spec["key"])
    update = ""
    if not spec.get("incremental"):  # las tablas de solo agregar nunca se modifican
        sets = ", ".join([f"t.{n} = s.{n}" for n in names if n not in spec["key"]] + ["t._loaded_at = current_timestamp()"])
        update = f"WHEN MATCHED THEN UPDATE SET {sets}"
    return (f"MERGE INTO {CATALOG}.{SCHEMA}.{table} t "
            f"USING (SELECT * FROM read_files('{path}', format => 'json', schema => '{schema}')) s ON {on} "
            f"{update} WHEN NOT MATCHED THEN INSERT ({', '.join(names)}, _loaded_at) "
            f"VALUES ({', '.join('s.' + n for n in names)}, current_timestamp())")


def load_table(cur, remote, tmp, table, spec):
    after = 0
    if spec.get("incremental"):
        cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {CATALOG}.{SCHEMA}.{table}")
        after = cur.fetchone()[0]
    names = [n for n, _ in spec["cols"]]
    volume_path = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/{table}.jsonl"
    local = Path(tmp) / f"{table}.jsonl"
    sent = 0
    for rows in pages(remote, spec, after):
        with open(local, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(dict(zip(names, r)), ensure_ascii=False) + "\n")
        cur.execute(f"PUT '{local.as_posix()}' INTO '{volume_path}' OVERWRITE")
        cur.execute(merge(table, spec, volume_path))
        sent += len(rows)
    print(f"  {table}: {sent} filas enviadas" + (f" (después del id {after})" if spec.get("incremental") else ""),
          flush=True)


def main():
    load_env()
    need = ["TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "DATABRICKS_HOST", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit(f"Faltan variables de entorno: {', '.join(missing)}")
    remote = Turso(os.environ["TURSO_DATABASE_URL"], os.environ["TURSO_AUTH_TOKEN"])

    with tempfile.TemporaryDirectory() as tmp, sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://").rstrip("/"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
        staging_allowed_local_path=tmp,
    ) as conn:
        cur = conn.cursor()
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
        cur.execute(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")
        print("Cargando Turso -> Databricks ...", flush=True)
        for table, spec in TABLES.items():
            cur.execute(ddl(table, spec))
            load_table(cur, remote, tmp, table, spec)

        bad = []
        for table in TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {CATALOG}.{SCHEMA}.{table}")
            here = cur.fetchone()[0]
            there = remote.execute(f"SELECT COUNT(*) FROM {table}")[0][0]
            print(f"  {table}: Turso {there} | Databricks {here}", flush=True)
            if here != there:
                bad.append(table)
    if bad:
        sys.exit(f"Los conteos no coinciden en: {', '.join(bad)}")
    print("Listo. Databricks quedó al día con Turso.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
