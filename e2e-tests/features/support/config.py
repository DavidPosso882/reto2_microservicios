"""Configuración del proyecto E2E leída de variables de entorno.

Ningún secreto vive en los `.feature` ni en este archivo: las credenciales se
inyectan por entorno y este módulo solo las lee cuando un step las necesita.

Variables soportadas
--------------------
BASE_URL
    URL base del gateway. Default: ``http://localhost:8080``.
SMOKE_PATH
    Endpoint público usado por el humo. Default: ``/health`` (ver README).
ADMIN_EMAIL / ADMIN_PASSWORD
    Credenciales del rol ADMIN para el login de Antecedentes (Background).
USER_EMAIL / USER_PASSWORD
    Credenciales del rol USER para el login de Antecedentes (Background).
HTTP_TIMEOUT
    Timeout HTTP en segundos. Default: ``10``.
"""

from __future__ import annotations

import os
from typing import Tuple

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_SMOKE_PATH = "/health"
DEFAULT_HTTP_TIMEOUT = "10"


def base_url() -> str:
    """URL del gateway sin barra final."""
    return os.environ.get("BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def smoke_path() -> str:
    """Endpoint público que usa el escenario de humo."""
    return os.environ.get("SMOKE_PATH", DEFAULT_SMOKE_PATH)


def http_timeout() -> float:
    """Timeout HTTP en segundos."""
    return float(os.environ.get("HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT))


def credentials_for(role: str) -> Tuple[str, str]:
    """Devuelve ``(email, password)`` del rol indicado, leídos del entorno.

    El rol se normaliza a mayúsculas: ``"admin"`` -> ``ADMIN_EMAIL`` /
    ``ADMIN_PASSWORD``. Falla con un mensaje claro si falta alguna variable,
    pero nunca imprime el valor de la contraseña.
    """
    prefix = role.strip().upper()
    email = os.environ.get(f"{prefix}_EMAIL")
    password = os.environ.get(f"{prefix}_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            f"Faltan credenciales para el rol {prefix}: definí {prefix}_EMAIL "
            f"y {prefix}_PASSWORD en el entorno antes de ejecutar behave."
        )
    return email, password
