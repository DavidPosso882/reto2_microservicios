#!/usr/bin/env python3
"""Aplica el bot real de Telegram al contact point aprovisionado (T6).

Lee TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID del .env local (nunca en git) y
genera observabilidad/grafana/provisioning/alerting/contact-points.yml desde
contact-points.yml.template (el .yml generado tampoco va a git).

Por qué por archivo y no por $VAR ni por API: Grafana infiere tipo numérico al
expandir variables de entorno y rechaza los chat_id numéricos reales
("cannot unmarshal number into Config.chatid", hallazgo T6); y la API rechaza
reescribir objetos con provenance 'file'. Entre comillas y hardcodeado en el
fichero generado, bootea y envía (verificado).

Uso:
  python3 scripts/grafana-set-telegram.py [--no-restart]
  python3 scripts/grafana-set-telegram.py --verify-only
"""
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERTING = os.path.join(ROOT, "observabilidad", "grafana", "provisioning", "alerting")
TEMPLATE = os.path.join(ALERTING, "contact-points.yml.template")
GENERATED = os.path.join(ALERTING, "contact-points.yml")
GRAFANA = os.environ.get("GRAFANA_URL", "http://localhost:3000")
RECEIVER_UID = "reto8-telegram-receiver"


def read_env(path):
    vals = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def api_get(path, password):
    import base64

    req = urllib.request.Request(GRAFANA + path, method="GET")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"admin:{password}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def main():
    env = read_env(os.path.join(ROOT, ".env"))
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat = env.get("TELEGRAM_CHAT_ID", "")
    gpass = env.get("GRAFANA_ADMIN_PASSWORD", "admin")
    if "--verify-only" not in sys.argv:
        if not token or "PLACEHOLDER" in token or not chat or "PLACEHOLDER" in chat or chat == "000000000":
            print("ERROR: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID reales no están en .env", file=sys.stderr)
            return 2
        with open(TEMPLATE, encoding="utf-8") as fh:
            content = fh.read()
        content = content.replace("__TELEGRAM_BOT_TOKEN__", token).replace("__TELEGRAM_CHAT_ID__", chat)
        if "__TELEGRAM_" in content:
            print("ERROR: el template tiene marcadores sin reemplazo", file=sys.stderr)
            return 1
        with open(GENERATED, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(GENERATED, 0o644)  # legible por el uid grafana vía bind-mount; fuera de git
        print("contact-points.yml generado (modo 600, fuera de git)")
        if "--no-restart" not in sys.argv:
            r = subprocess.run(["docker", "compose", "restart", "grafana"], cwd=ROOT, capture_output=True, text=True, timeout=120)
            print(r.stdout.strip() or r.stderr.strip()[-200:])
            import time

            for _ in range(12):
                time.sleep(5)
                try:
                    st, _ = api_get("/api/org", gpass)
                    if st == 200:
                        break
                except Exception:
                    pass
    st, cps = api_get("/api/v1/provisioning/contact-points", gpass)
    if st != 200:
        print("Grafana no responde (HTTP %s); ¿está arriba?" % st)
        return 1
    for cp in cps:
        if cp.get("uid") == RECEIVER_UID:
            print("receiver:", cp["name"], "| chatid:", cp["settings"].get("chatid"), "| provenance:", cp.get("provenance"))
            return 0
    print("receiver no encontrado")
    return 1


if __name__ == "__main__":
    sys.exit(main())
