"""Pasos comunes del proyecto E2E (Reto 6).

Humo del gateway
----------------
``Dado sistema desplegado y operativo`` pega a un endpoint público real del
gateway (``SMOKE_PATH``, default ``/health``) y guarda la respuesta en
``context.last_response``; el ``Entonces`` solo verifica el código.

Endpoint elegido en P2 (sondeo contra http://localhost:8080):

* ``GET /health``              -> 200 ``{"status":"ok","service":"api-gateway"}``  <- elegido
* ``GET /api-docs``            -> 401
* ``GET /docs``                -> 401
* ``GET /notificaciones/docs`` -> 200 (depende de notificaciones-service)
* ``GET /auth/docs``           -> 401
* ``GET /empleados``           -> 401 (prueba de vida del gateway si no hubiera 200)

Se prefiere ``/health``: es el 200 del propio gateway, no depende de otro
servicio y no exige token (Reto 5: el resto de rutas pasan por JWT).
"""

from __future__ import annotations

import requests
from behave import given, then


@given("sistema desplegado y operativo")
def step_sistema_operativo(context):
    """Pega al endpoint público de humo y guarda la respuesta."""
    try:
        context.last_response = context.api.get(context.smoke_path)
    except requests.RequestException as exc:
        raise AssertionError(
            f"No se pudo contactar {context.base_url}{context.smoke_path}: {exc}. "
            "¿Está el stack levantado?"
        ) from exc


@then("respuesta código {status:d}")
def step_respuesta_codigo(context, status):
    """Verifica el código HTTP de la última respuesta."""
    response = context.last_response
    assert response is not None, (
        "No hay respuesta HTTP registrada en context.last_response; "
        "¿se ejecutó antes un paso que haga una petición?"
    )

    last = getattr(context.api, "last_request", None)
    where = f"{last[0]} {last[1]}" if last else "la última petición"
    assert response.status_code == status, (
        f"{where} devolvió {response.status_code}, se esperaba {status}. "
        f"Cuerpo (recorte): {response.text[:500]!r}"
    )


@then("la respuesta tiene código {status:d}")
def step_respuesta_tiene_codigo(context, status):
    """Alias explícito de ``respuesta código N`` para futuros features."""
    step_respuesta_codigo(context, status)
