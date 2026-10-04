"""Envía un correo con los trabajos que fallaron en una corrida de GitHub Actions.

Lo lanza el último trabajo del flujo diario cuando algo falló. Pregunta a la API de GitHub qué
trabajos terminaron en 'failure' (y en qué paso) y manda el resumen por SMTP. Solo usa la
biblioteca estándar.

Variables de entorno:
    GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID   las pone GitHub Actions
    SMTP_USER       cuenta que envía (p. ej. una de Gmail)
    SMTP_PASSWORD   contraseña de aplicación de esa cuenta (no la contraseña normal)
    NOTIFY_EMAIL    quién recibe el aviso (por defecto, SMTP_USER)
    SMTP_HOST       por defecto smtp.gmail.com (puerto 465, SSL)

Uso de prueba, sin enviar nada:
    python scraper/notify_failure.py --dry-run --conclusion success
"""
import argparse
import json
import os
import smtplib
import sys
import urllib.request
from email.message import EmailMessage

API = "https://api.github.com"


def github(path):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=headers), timeout=30) as r:
        return json.load(r)


def failed_jobs(repo, run_id, conclusion):
    jobs = github(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100&filter=latest")["jobs"]
    return [j for j in jobs if j["conclusion"] == conclusion]


def build_message(repo, run_id, jobs, conclusion):
    run = github(f"/repos/{repo}/actions/runs/{run_id}")
    lines = []
    for j in jobs:
        step = next((s["name"] for s in j["steps"] if s["conclusion"] == conclusion), None)
        lines.append(f"- {j['name']}" + (f": falló el paso «{step}»" if step else "") + f"\n  {j['html_url']}")
    names = ", ".join(j["name"] for j in jobs)
    body = (
        f"Fallaron {len(jobs)} trabajo(s) en «{run['name']}» (intento {run['run_attempt']}):\n\n"
        + "\n".join(lines)
        + f"\n\nCorrida completa: {run['html_url']}\n\n"
        "Qué hacer:\n"
        "- Si el error fue pasajero (red, 429, 5xx): en la corrida, botón «Re-run failed jobs».\n"
        "  Repite solo lo que falló.\n"
        "- Si hubo que corregir código: Actions > Descarga diaria de precios > Run workflow y elegir\n"
        "  la tienda en la lista (repetir el intento viejo usaría el código viejo).\n"
    )
    msg = EmailMessage()
    msg["Subject"] = f"Comparador de precios: falló {names}"
    msg.set_content(body)
    return msg


def main():
    ap = argparse.ArgumentParser(description="Avisa por correo de los trabajos fallidos de una corrida")
    ap.add_argument("--dry-run", action="store_true", help="muestra el correo en vez de enviarlo")
    ap.add_argument("--conclusion", default="failure", help="conclusión a buscar (para pruebas)")
    args = ap.parse_args()

    repo, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    if not repo or not run_id:
        sys.exit("Faltan GITHUB_REPOSITORY y GITHUB_RUN_ID (los pone GitHub Actions)")
    jobs = failed_jobs(repo, run_id, args.conclusion)
    if not jobs:
        print(f"Ningún trabajo con conclusión '{args.conclusion}' en la corrida {run_id}; no se envía nada.")
        return
    msg = build_message(repo, run_id, jobs, args.conclusion)

    if args.dry_run:
        print(f"Asunto: {msg['Subject']}\n\n{msg.get_content()}")
        return
    user, password = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    if not user or not password:
        sys.exit("Faltan SMTP_USER y SMTP_PASSWORD: el aviso por correo no está configurado")
    msg["From"] = user
    msg["To"] = os.environ.get("NOTIFY_EMAIL") or user
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465, timeout=30) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    print(f"Correo enviado a {msg['To']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
