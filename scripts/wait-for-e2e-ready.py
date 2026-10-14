#!/usr/bin/env python3
"""Espera el stack E2E y deja el ADMIN demo listo (solo stdlib).

Reto 7 P4: tras `compose up`, espera que el gateway responda /health
(timeout 120 s) y deja 20 s de asentamiento para la topología RabbitMQ
(las colas deben existir antes de los primeros eventos; ver Reto 4).
Luego hace bootstrap del ADMIN demo si la tabla está vacía (tolerando 4xx
si ya existe) para que run_bdd.sh use sus credenciales por defecto.

Uso: BASE_URL=http://localhost:8080 python3 scripts/wait-for-e2e-ready.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
TIMEOUT_S = int(os.environ.get("E2E_WAIT_TIMEOUT_S", "120"))
SETTLE_S = int(os.environ.get("E2E_SETTLE_S", "20"))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@empresa.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")


def get(path: str):
    with urllib.request.urlopen(BASE_URL + path, timeout=5) as r:
        return r.status, r.read()


def post(path: str, payload: dict):
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read()


def main() -> int:
    deadline = time.time() + TIMEOUT_S
    while time.time() < deadline:
        try:
            status, _ = get("/health")
            if status == 200:
                break
        except Exception:
            pass
        time.sleep(3)
    else:
        print("wait-for-e2e-ready: gateway sin /health tras el timeout", file=sys.stderr)
        return 1
    print("wait-for-e2e-ready: gateway ok, asentando topología...")
    time.sleep(SETTLE_S)
    try:
        status, _ = post("/auth/bootstrap", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        print(f"wait-for-e2e-ready: bootstrap {status} (ADMIN demo listo)")
    except urllib.error.HTTPError as e:
        print(f"wait-for-e2e-ready: bootstrap {e.code} (ya existía, se sigue)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
