#!/usr/bin/env python3
"""Descarga el binario standalone de Docker Compose (solo stdlib, sin curl/apt).

Reto 7 P4: los agentes efímeros (python:slim) no traen ni docker ni compose;
este helper deja `.ci-tools/docker-compose` en el workspace para las etapas
Package (build/push) y E2E (up/logs/down). El binario standalone habla directo
con el socket del host, no necesita el CLI de docker.

Uso: python3 scripts/fetch-compose.py [--dir .ci-tools]
"""
import os
import stat
import subprocess
import sys
import urllib.request

COMPOSE_VERSION = "v2.29.7"
URL = (
    "https://github.com/docker/compose/releases/download/"
    f"{COMPOSE_VERSION}/docker-compose-linux-x86_64"
)

TARGET_DIR = sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else ".ci-tools"


def main() -> int:
    dest = os.path.join(TARGET_DIR, "docker-compose")
    if os.path.isfile(dest):
        print(f"fetch-compose: {dest} ya existe, reutilizando")
    else:
        os.makedirs(TARGET_DIR, exist_ok=True)
        print(f"fetch-compose: descargando {URL}")
        urllib.request.urlretrieve(URL, dest)
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    out = subprocess.run([dest, "version", "--short"], capture_output=True, text=True)
    print(f"fetch-compose: {dest} -> {out.stdout.strip() or out.stderr.strip()}")
    return 0 if out.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
