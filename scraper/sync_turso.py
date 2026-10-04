"""Sube a Turso la última descarga guardada en el SQLite local.

El scraper escribe en un SQLite local (rápido). Este script copia esa descarga a la base
de Turso en lotes, para conservar el historial fuera de la máquina que corrió el scraper.
Se puede repetir sin duplicar datos: si una sincronización se corta, basta volver a lanzarla.

Variables de entorno (o un archivo .env en la raíz del proyecto):
    TURSO_DATABASE_URL   p. ej. libsql://mi-base-mi-org.turso.io
    TURSO_AUTH_TOKEN     token de la base

Uso:
    python scraper/sync_turso.py                      # sincroniza la última descarga
    python scraper/sync_turso.py --run-id 2           # una descarga concreta
    python scraper/sync_turso.py --fail-unless-ok     # sale con error si la descarga no quedó 'ok'
"""
import argparse
import base64
import os
import sqlite3
import sys
import time
from pathlib import Path

import httpx

from db import DB_PATH, SCHEMA

BATCH_ROWS = 100  # productos (con su precio) por petición
MAX_ATTEMPTS = 5
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_env():
    """Lee NOMBRE=valor de .env sin pisar variables ya definidas."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def encode(value):
    """Valor de Python -> valor del protocolo HTTP de Turso (Hrana)."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def decode(value):
    kind = value["type"]
    if kind == "null":
        return None
    if kind == "integer":
        return int(value["value"])
    if kind == "float":
        return float(value["value"])
    if kind == "blob":
        return base64.b64decode(value["base64"])
    return value["value"]


class Turso:
    """Cliente mínimo del protocolo HTTP de Turso (/v2/pipeline)."""

    def __init__(self, url, token):
        self.endpoint = url.replace("libsql://", "https://").rstrip("/") + "/v2/pipeline"
        self.http = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=120)

    def _post(self, requests):
        body = {"requests": requests + [{"type": "close"}]}
        for attempt in range(MAX_ATTEMPTS):
            try:
                r = self.http.post(self.endpoint, json=body)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPError(f"HTTP {r.status_code}")
                if r.status_code != 200:
                    sys.exit(f"Turso respondió HTTP {r.status_code}: {r.text[:300]}")
                return r.json()["results"][0]
            except httpx.HTTPError as e:
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                wait = 5 * 2**attempt
                print(f"  reintento en {wait}s ({e})", flush=True)
                time.sleep(wait)

    @staticmethod
    def _stmt(sql, args):
        return {"sql": sql, "args": [encode(a) for a in args]}

    def execute(self, sql, args=()):
        """Ejecuta una sentencia y devuelve sus filas como listas."""
        res = self._post([{"type": "execute", "stmt": self._stmt(sql, args)}])
        if res["type"] == "error":
            raise RuntimeError(f"Turso: {res['error']['message']}\n  SQL: {sql[:200]}")
        return [[decode(v) for v in row] for row in res["response"]["result"]["rows"]]

    def batch(self, stmts):
        """Ejecuta varias sentencias en una transacción: o entran todas o ninguna."""
        if not stmts:
            return
        steps = [{"stmt": {"sql": "BEGIN"}}]
        for i, (sql, args) in enumerate(stmts):
            steps.append({"stmt": self._stmt(sql, args), "condition": {"type": "ok", "step": i}})
        commit = len(steps)
        steps.append({"stmt": {"sql": "COMMIT"}, "condition": {"type": "ok", "step": commit - 1}})
        steps.append({"stmt": {"sql": "ROLLBACK"},
                      "condition": {"type": "not", "cond": {"type": "ok", "step": commit}}})
        res = self._post([{"type": "batch", "batch": {"steps": steps}}])
        if res["type"] == "error":
            raise RuntimeError(f"Turso: {res['error']['message']}")
        result = res["response"]["result"]
        errors = [e for e in result["step_errors"][: commit + 1] if e]
        if errors or result["step_results"][commit] is None:
            msg = errors[0]["message"] if errors else "no se pudo confirmar la transacción"
            raise RuntimeError(f"Turso: {msg}")


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


def sync(remote, local, run_id):
    local.executescript(SCHEMA)  # bases creadas con una versión anterior del esquema
    run =local.execute("SELECT * FROM scrape_runs WHERE id = ?", (run_id,)).fetchone()
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
    done = 0
    while True:
        chunk = rows.fetchmany(BATCH_ROWS)
        if not chunk:
            break
        stmts = []
        for r in chunk:
            stmts.append((UPSERT_PRODUCT, (store_id, *r[0:13])))
            stmts.append((INSERT_PRICE, (remote_run, r[13], r[14], r[15], r[16], store_id, r[0], remote_run)))
        remote.batch(stmts)
        done += len(chunk)
        if done % (BATCH_ROWS * 10) == 0 or done == total:
            print(f"  {done}/{total} precios subidos", flush=True)

    run_cats = local.execute("SELECT category_path, name, reported_total, downloaded, retries "
                             "FROM scrape_run_categories WHERE run_id = ?", (run_id,)).fetchall()
    remote.batch([
        ("""INSERT OR REPLACE INTO scrape_run_categories
              (run_id, category_path, name, reported_total, downloaded, retries) VALUES (?, ?, ?, ?, ?, ?)""",
         (remote_run, *c))
        for c in run_cats
    ])

    uploaded = remote.execute("SELECT COUNT(*) FROM prices WHERE run_id = ?", (remote_run,))[0][0]
    if uploaded != total:
        sys.exit(f"Faltan datos en Turso: subidos {uploaded} de {total}. Vuelve a lanzar la sincronización.")
    remote.execute(
        "UPDATE scrape_runs SET finished_at = ?, status = ?, products_seen = ?, items_seen = ?, notes = ? WHERE id = ?",
        (run["finished_at"], run["status"], run["products_seen"], run["items_seen"], run["notes"], remote_run),
    )
    print(f"Listo. Descarga {run['started_at']} sincronizada como id {remote_run} ({uploaded} precios).")
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
