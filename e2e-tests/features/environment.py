"""Hooks de Behave del proyecto E2E (Reto 6, P2/P3).

Ciclo de vida del contexto
--------------------------
Behave crea un ``context`` nuevo por escenario y llama a ``before_scenario``
antes de cada uno. Aquí se deja explícito el estado limpio:

* ``context.api``: instancia nueva de :class:`support.api_client.ApiClient`.
* ``context.run_id``: sufijo uuid4 único por escenario (P3). Los datos de
  prueba (``E2E-P3-<run_id>``) lo usan para no chocar entre corridas ni entre
  escenarios, que así quedan independientes.
* ``context.token``: token vigente del escenario (``None`` al inicio).
* ``context.tokens``: tokens por rol (por si un escenario usa más de uno).
* ``context.user_employee_id`` / ``context.user_email``: cuenta USER sintética
  activada por el flujo del Punto 3 (``None`` hasta que se cree).
* ``context.created_employee_id``: empleado dado de alta por el escenario
  ADMIN, usado por el DELETE (``None`` hasta que se cree).
* ``context.onboarding_employee_id`` / ``context.onboarding_email``: empleado
  y email únicos del escenario de onboarding del Punto 4 (``None`` hasta que
  se registren).
* ``context.onboarding_security_notification``: notificación de tipo SEGURIDAD
  con el token de activación, ya esperada con polling (``None`` hasta que
  llegue). Es la prueba observable de que auth-service creó la cuenta.
* ``context.onboarding_welcome_notification``: notificación BIENVENIDA del
  medio email simulado, ya esperada con polling (``None`` hasta que llegue).
* ``context.active_employee_id`` / ``context.active_employee_email`` /
  ``context.active_employee_password`` /
  ``context.active_employee_reset_token``: precondición compleja del Punto 5
  (vacaciones y offboarding). El paso de Antecedentes crea un empleado desde
  cero, activa su cuenta con el reset token de la notificación y deja la
  sesión como ADMIN. Los cuatro campos son ``None`` hasta que se ejecute ese
  paso.
* ``context.vacation_period_id``: id del período programado por el escenario
  de vacaciones (``None`` hasta que se programe uno).
* ``context.vacation_period_dates``: tupla ``(fechaInicio, fechaFin)`` del
  último período programado (``None`` hasta entonces).
* ``context.p5_senuelos``: cuentas satélite (empleado + email) creadas por el
  escenario del ciclo para ampliar la ventana de suspensión observable
  (``[]`` al inicio).
* ``context.security_notifications_snapshot``: ids de las notificaciones
  SEGURIDAD observadas antes de probar la recuperación de contraseña del
  retirado (``None`` hasta ese momento).
* ``context.last_response``: última respuesta HTTP observada.

Los valores de ``BASE_URL`` y ``SMOKE_PATH`` se leen del entorno en cada
escenario (ver ``support/config.py``), sin secretos en los ``.feature``.
"""

from __future__ import annotations

import uuid

from support import config
from support.api_client import ApiClient


def before_scenario(context, scenario):
    """Estado HTTP limpio y aislado para cada escenario."""
    context.base_url = config.base_url()
    context.smoke_path = config.smoke_path()
    context.api = ApiClient(context.base_url)
    context.run_id = uuid.uuid4().hex
    context.token = None
    context.tokens = {}
    context.user_employee_id = None
    context.user_email = None
    context.created_employee_id = None
    context.onboarding_employee_id = None
    context.onboarding_email = None
    context.onboarding_security_notification = None
    context.onboarding_welcome_notification = None
    context.active_employee_id = None
    context.active_employee_email = None
    context.active_employee_password = None
    context.active_employee_reset_token = None
    context.vacation_period_id = None
    context.vacation_period_dates = None
    context.p5_senuelos = []
    context.security_notifications_snapshot = None
    context.last_response = None


def after_scenario(context, scenario):
    """Cierra la sesión HTTP; el contexto se descarta con el escenario."""
    api = getattr(context, "api", None)
    if api is not None:
        api.close()
