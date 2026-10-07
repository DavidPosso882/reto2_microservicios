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
E2E_USER_PASSWORD
    Password con el que el flujo E2E activa la cuenta USER sintética del
    Punto 3 (alta + reset). Default: ``User1234``. No es un secreto: la
    cuenta la crea la propia corrida y se desactiva (= se retira) en el
    escenario ADMIN.
HTTP_TIMEOUT
    Timeout HTTP en segundos. Default: ``10``.
"""

from __future__ import annotations

import os
from typing import Tuple

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_SMOKE_PATH = "/health"
DEFAULT_HTTP_TIMEOUT = "10"
DEFAULT_E2E_USER_PASSWORD = "User1234"

# Departamento sintético compartido por los escenarios RBAC del Punto 3: el
# Antecedentes lo asegura (crea si falta) con el token ADMIN, de forma
# idempotente, antes de registrar empleados E2E.
E2E_DEPARTMENT_ID = "E2E-P3-DEPT"


def base_url() -> str:
    """URL del gateway sin barra final."""
    return os.environ.get("BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def smoke_path() -> str:
    """Endpoint público que usa el escenario de humo."""
    return os.environ.get("SMOKE_PATH", DEFAULT_SMOKE_PATH)


def http_timeout() -> float:
    """Timeout HTTP en segundos."""
    return float(os.environ.get("HTTP_TIMEOUT", DEFAULT_HTTP_TIMEOUT))


def user_activation_password() -> str:
    """Password de la cuenta USER sintética que activa el flujo del Punto 3.

    Se puede sobrescribir con ``E2E_USER_PASSWORD``; el default documenta el
    valor usado por los escenarios, pero no es una credencial de producción.
    """
    return os.environ.get("E2E_USER_PASSWORD", DEFAULT_E2E_USER_PASSWORD)


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
