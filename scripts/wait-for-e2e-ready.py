#!/usr/bin/env python3
"""Espera el stack E2E y deja el ADMIN demo listo (solo stdlib).

Reto 7 P4: tras `compose up`, espera que el gateway responda /health.
Luego hace bootstrap del ADMIN demo si la tabla está vacía (tolerando 4xx
si ya existe), inicia sesión y espera a que CADA servicio de negocio conteste
a través del gateway: el gateway arranca cuando los servicios están
"started", no listos, y empleados (Java + agente OTel del Reto 8) tarda más;
sin esta espera los primeros escenarios recibían 503 (build vacaciones #31).
Por último deja 20 s de asentamiento para la topología RabbitMQ (las colas
deben existir antes de los primeros eventos; ver Reto 4).

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
SERVICES_TIMEOUT_S = int(os.environ.get("E2E_SERVICES_TIMEOUT_S", "300"))
SETTLE_S = int(os.environ.get("E2E_SETTLE_S", "20"))
# Prefijos de negocio del gateway. La ruta de sondeo no existe a propósito:
# un 404/400 del servicio prueba que está vivo; 502/503/504 los genera el
# gateway cuando el servicio aún no responde.
SERVICES = ["empleados", "departamentos", "perfiles", "notificaciones", "vacaciones"]
NOT_READY = {502, 503, 504}
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


def status_of(path: str, token: str = None) -> int:
    """Código HTTP de un GET (0 si no hay conexión); nunca lanza."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(BASE_URL + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def bootstrap_and_login(deadline: float):
    """Crea el ADMIN demo (si falta) e inicia sesión; reintenta mientras auth arranca."""
    bootstrap_done = False
    while time.time() < deadline:
        if not bootstrap_done:
            try:
                status, _ = post("/auth/bootstrap", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
                print(f"wait-for-e2e-ready: bootstrap {status} (ADMIN demo listo)")
                bootstrap_done = True
            except urllib.error.HTTPError as e:
                if e.code not in NOT_READY:
                    print(f"wait-for-e2e-ready: bootstrap {e.code} (ya existía, se sigue)")
                    bootstrap_done = True
            except Exception:
                pass
        if bootstrap_done:
            try:
                _, body = post("/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
                payload = json.loads(body)
                token = payload.get("accessToken") or payload.get("token")
                if token:
                    return token
            except Exception:
                pass
        time.sleep(3)
    return None


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
    print("wait-for-e2e-ready: gateway ok, esperando a los servicios...")

    services_deadline = time.time() + SERVICES_TIMEOUT_S
    token = bootstrap_and_login(services_deadline)
    if not token:
        print("wait-for-e2e-ready: no se pudo iniciar sesión como ADMIN", file=sys.stderr)
        return 1

    pending = list(SERVICES)
    while pending and time.time() < services_deadline:
        for name in list(pending):
            code = status_of(f"/{name}/__e2e_ready__", token)
            if code and code not in NOT_READY:
                print(f"wait-for-e2e-ready: {name} responde ({code})")
                pending.remove(name)
        if pending:
            time.sleep(3)
    if pending:
        print(f"wait-for-e2e-ready: sin respuesta tras el timeout: {', '.join(pending)}", file=sys.stderr)
        return 1

    print(f"wait-for-e2e-ready: servicios listos, asentando topología ({SETTLE_S}s)...")
    time.sleep(SETTLE_S)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
