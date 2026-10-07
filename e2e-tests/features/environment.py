"""Hooks de Behave del proyecto E2E (Reto 6, P2).

Ciclo de vida del contexto
--------------------------
Behave crea un ``context`` nuevo por escenario y llama a ``before_scenario``
antes de cada uno. Aquí se deja explícito el estado limpio:

* ``context.api``: instancia nueva de :class:`support.api_client.ApiClient`.
* ``context.token``: token vigente del escenario (``None`` al inicio).
* ``context.tokens``: tokens por rol (por si un escenario usa más de uno).
* ``context.last_response``: última respuesta HTTP observada.

Los valores de ``BASE_URL`` y ``SMOKE_PATH`` se leen del entorno en cada
escenario (ver ``support/config.py``), sin secretos en los ``.feature``.
"""

from __future__ import annotations

from support import config
from support.api_client import ApiClient


def before_scenario(context, scenario):
    """Estado HTTP limpio y aislado para cada escenario."""
    context.base_url = config.base_url()
    context.smoke_path = config.smoke_path()
    context.api = ApiClient(context.base_url)
    context.token = None
    context.tokens = {}
    context.last_response = None


def after_scenario(context, scenario):
    """Cierra la sesión HTTP; el contexto se descarta con el escenario."""
    api = getattr(context, "api", None)
    if api is not None:
        api.close()
