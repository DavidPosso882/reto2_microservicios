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
E2E_P5_SENUELOS
    Cantidad de cuentas/periodos satélite que el escenario de ciclo del P5
    crea en el MISMO tick del scheduler para ampliar la ventana de
    suspensión observable del empleado protagonista (ver README, control
    del tiempo). Default: ``8``; ``0`` desactiva la amplificación.
E2E_P5_LOGIN_INTERVAL_MS
    Intervalo entre reintentos del polling de login del P5 (el ciclo
    suspender/reactivar y el bloqueo del retirado). Default: ``100``.
E2E_P5_SCHEDULER_TIMEOUT_S
    Presupuesto máximo de espera del tick del scheduler (default 60 s) hasta
    observar el 401 del ciclo. Default: ``75`` (cubre el intervalo completo
    más el procesamiento de eventos).
E2E_P5_REACTIVACION_TIMEOUT_S
    Presupuesto de espera del 200 posterior a la suspensión; la reactivación
    ocurre en el mismo tick, así que es corto. Default: ``20``.
E2E_P5_VENTANA_NEGATIVA_S
    Ventana de observación para comprobaciones negativas del offboarding
    (el retirado nunca vuelve a poder entrar y la recuperación no emite
    token). No es una espera de un evento: es el presupuesto de evidencia
    de una ausencia. Default: ``10``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Tuple

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_SMOKE_PATH = "/health"
DEFAULT_HTTP_TIMEOUT = "10"
DEFAULT_E2E_USER_PASSWORD = "User1234"
DEFAULT_P5_SENUELOS = "8"
DEFAULT_P5_LOGIN_INTERVAL_MS = "100"
DEFAULT_P5_SCHEDULER_TIMEOUT_S = "75"
DEFAULT_P5_REACTIVACION_TIMEOUT_S = "20"
DEFAULT_P5_VENTANA_NEGATIVA_S = "10"

# Departamento sintético compartido por los escenarios RBAC del Punto 3: el
# Antecedentes lo asegura (crea si falta) con el token ADMIN, de forma
# idempotente, antes de registrar empleados E2E.
E2E_DEPARTMENT_ID = "E2E-P3-DEPT"

# Departamento sintético del Punto 4 (onboarding asíncrono). Se asegura igual
# que el de P3 (GET; si da 404 se crea con ADMIN) y lo usan todos los
# escenarios de onboarding como único estado compartido: los empleados siguen
# siendo únicos por escenario.
E2E_P4_DEPARTMENT_ID = "E2E-P4-DEPT"

# Departamento sintético del Punto 5 (vacaciones y offboarding). Igual que en
# P3/P4: el Antecedentes lo asegura de forma idempotente y los empleados de
# cada escenario (incluidos los satélite del ciclo) son únicos.
E2E_P5_DEPARTMENT_ID = "E2E-P5-DEPT"


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


def p5_senuelos() -> int:
    """Cantidad de cuentas/periodos satélite del ciclo del P5 (>= 0).

    Ver el README (control del tiempo): en un tick del scheduler todas las
    transiciones ocurren seguidas y la ventana de suspensión de una sola
    cuenta es de milisegundos. Los satélite se procesan en el mismo tick y
    estiran esa ventana ~``cantidad * tiempo_de_procesamiento`` para que el
    login 401 sea observable con polling.
    """
    return max(0, int(os.environ.get("E2E_P5_SENUELOS", DEFAULT_P5_SENUELOS)))


def p5_login_interval_ms() -> int:
    """Intervalo (ms) del polling de login del P5 (>= 1)."""
    return max(1, int(os.environ.get("E2E_P5_LOGIN_INTERVAL_MS", DEFAULT_P5_LOGIN_INTERVAL_MS)))


def p5_scheduler_timeout_s() -> float:
    """Presupuesto (s) de espera del tick del scheduler del P5 (> 0)."""
    return max(
        1.0,
        float(os.environ.get("E2E_P5_SCHEDULER_TIMEOUT_S", DEFAULT_P5_SCHEDULER_TIMEOUT_S)),
    )


def p5_reactivacion_timeout_s() -> float:
    """Presupuesto (s) de espera del login 200 tras la suspensión (> 0)."""
    return max(
        1.0,
        float(
            os.environ.get(
                "E2E_P5_REACTIVACION_TIMEOUT_S", DEFAULT_P5_REACTIVACION_TIMEOUT_S
            )
        ),
    )


def p5_ventana_negativa_s() -> float:
    """Ventana (s) de evidencia de las comprobaciones negativas (> 0)."""
    return max(
        1.0,
        float(os.environ.get("E2E_P5_VENTANA_NEGATIVA_S", DEFAULT_P5_VENTANA_NEGATIVA_S)),
    )


def hoy_utc() -> str:
    """Fecha de hoy en UTC con formato ``YYYY-MM-DD``.

    Los contenedores del stack (vacaciones-service, auth-service, Postgres)
    corren en UTC y el scheduler decide el ciclo de vida con ``Date.today``.
    El runner puede estar en otra zona horaria (p. ej. UTC-5), así que el P5
    calcula las fechas en UTC para no desfasarse cerca de la medianoche.
    """
    return datetime.now(timezone.utc).date().isoformat()


def fecha_utc(dias: int) -> str:
    """Fecha UTC de hoy + ``dias`` con formato ``YYYY-MM-DD``."""
    return (datetime.now(timezone.utc).date() + timedelta(days=dias)).isoformat()


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
