"""Piezas compartidas por los scripts de sincronización: lectura de .env y cliente de Turso."""
import base64
import os
import sys
import time
from pathlib import Path

import httpx

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
