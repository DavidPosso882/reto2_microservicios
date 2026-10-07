"""Autenticación para los Antecedentes (Background) y cuentas sintéticas E2E.

Cómo se gestiona el login (Reto 5)
----------------------------------
El gateway exige JWT en las rutas de negocio. En vez de repetir el login en
cada escenario, se usa un ``Antecedentes`` (Background) que ejecuta este paso
antes de cada escenario del feature:

    # language: es
    Característica: Consulta protegida
      Antecedentes:
        Dado que inicio sesión como "admin"

      Escenario: ...
        ...

El paso hace ``POST /auth/login`` a través del gateway con las credenciales
del entorno, guarda el token en ``context.token`` (y en
``context.tokens["admin"]``) y lo inyecta como ``Authorization: Bearer`` en la
sesión HTTP del escenario. Un escenario nuevo = contexto nuevo = token nuevo,
sin fugas entre escenarios.

Cómo se obtiene un token USER real (Reto 6, Punto 3)
----------------------------------------------------
No hay usuarios USER semilla: el flujo del Reto 5 crea la cuenta al registrar
un empleado. El paso ``Dado que tengo un token de usuario activo`` reproduce
el camino real, sin fabricar tokens:

1. ADMIN registra un empleado único ``E2E-P3-USER-<run_id>`` (``POST
   /empleados`` -> 201). El evento ``empleado.creado`` crea la cuenta USER en
   estado ``SUSPENDIDA_TEMPORAL`` dentro de auth-service (asíncrono vía
   RabbitMQ).
2. Se espera (polling simple y acotado) a que notificaciones-service reciba
   ``usuario.creado`` y guarde el token de activación en el mensaje de la
   notificación del empleado (``GET /notificaciones/{id}``).
3. ``POST /auth/reset-password`` con ese token activa la cuenta y fija la
   password de prueba.
4. ``POST /auth/login`` devuelve el access token USER de verdad, que queda en
   ``context.tokens["user"]`` y como Bearer de la sesión.

Credenciales (nunca en los ``.feature``)
----------------------------------------
* ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` para el rol ``"admin"``.
* ``USER_EMAIL`` / ``USER_PASSWORD`` para el rol ``"user"`` (cuentas ya
  existentes en el entorno).
* ``E2E_USER_PASSWORD`` (default ``User1234``) para la cuenta sintética que
  activa el punto anterior.

Si faltan, el escenario falla con un mensaje que indica la variable esperada.
"""

from __future__ import annotations

import re
import time

from behave import given

from support import config

# El mensaje de la notificación incluye el JWT de reset en prosa; se extraen
# sus tres segmentos base64url (header.payload.firma).
_RESET_TOKEN_RE = re.compile(r"([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")

# Espera acotada del evento asíncrono empleado.creado -> cuenta -> notificación.
_USER_RESET_TIMEOUT_S = 30.0
_USER_RESET_INTERVAL_S = 0.5


def _esperar_reset_token(context, empleado_id):
    """Espera a que llegue la notificación de activación y extrae el token.

    Polling simple y acotado (solo para este paso de preparación): el flujo de
    negocio del Punto 3 es síncrono; lo asíncrono es la creación de la cuenta
    por RabbitMQ. Devuelve el token o falla con diagnóstico si se agota el
    timeout.
    """
    limite = time.monotonic() + _USER_RESET_TIMEOUT_S
    ultimo_estado = None
    intentos = 0
    while time.monotonic() < limite:
        intentos += 1
        respuesta = context.api.get(f"/notificaciones/{empleado_id}")
        ultimo_estado = respuesta.status_code
        if respuesta.status_code == 200:
            for notificacion in respuesta.json():
                coincidencia = _RESET_TOKEN_RE.search(notificacion.get("mensaje", ""))
                if coincidencia:
                    return coincidencia.group(1)
        time.sleep(_USER_RESET_INTERVAL_S)

    raise AssertionError(
        f"No llegó la notificación con el token de activación de {empleado_id!r} "
        f"en {_USER_RESET_TIMEOUT_S:.0f}s (GET /notificaciones/{empleado_id} "
        f"respondió {ultimo_estado} en el último intento, {intentos} sondeos). "
        "¿Está auth-service consumiendo empleado.creado y el consumer de "
        "notificaciones levantado?"
    )


def _token_de_respuesta(respuesta, contexto):
    """Extrae el access token del login aceptando ``accessToken`` o ``token``."""
    payload = respuesta.json()
    token = payload.get("accessToken") or payload.get("token")
    assert token, (
        f"{contexto} respondió 200 pero sin token utilizable "
        f"(claves: {sorted(payload)!r})."
    )
    return token


@given('que inicio sesión como "{role}"')
def step_login(context, role):
    """Login contra /auth/login vía gateway y guarda el Bearer del escenario."""
    email, password = config.credentials_for(role)

    context.last_response = context.api.post(
        "/auth/login", json={"email": email, "password": password}
    )
    response = context.last_response

    assert response.status_code == 200, (
        f"POST /auth/login devolvió {response.status_code} para el rol "
        f"{role!r}; se esperaba 200. Cuerpo (recorte): {response.text[:500]!r}"
    )

    token = _token_de_respuesta(response, "POST /auth/login")

    context.token = token
    context.tokens[role.strip().lower()] = token
    context.api.set_token(token)


@given("que tengo un token de usuario activo")
def step_token_usuario_activo(context):
    """Crea y activa una cuenta USER real y deja su Bearer en el escenario.

    Requiere el token ADMIN del Antecedentes. El empleado y el email llevan el
    ``run_id`` del escenario (``E2E-P3-USER-<run_id>``), así que cada corrida
    crea una cuenta nueva y ningún escenario depende de otro.
    """
    admin_token = context.tokens.get("admin")
    assert admin_token, (
        "No hay token ADMIN en el escenario; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"` antes de activar la cuenta USER.'
    )
    context.api.set_token(admin_token)

    run_id = context.run_id
    empleado_id = f"E2E-P3-USER-{run_id}"
    email = f"e2e-p3-user-{run_id}@empresa.com"
    password_activacion = config.user_activation_password()
    context.user_employee_id = empleado_id
    context.user_email = email

    alta = context.api.post(
        "/empleados",
        json={
            "id": empleado_id,
            "nombre": "Usuario",
            "apellido": "E2E",
            "email": email,
            "numeroEmpleado": f"EMP-E2E-P3-USER-{run_id}",
            "cargo": "QA",
            "area": "Tecnología",
            "departamentoId": config.E2E_DEPARTMENT_ID,
            "fechaIngreso": "2026-01-15",
            "estado": "ACTIVO",
        },
    )
    assert alta.status_code == 201, (
        f"POST /empleados (ADMIN) devolvió {alta.status_code} al crear {empleado_id!r}; "
        f"se esperaba 201. Cuerpo (recorte): {alta.text[:500]!r}"
    )

    reset_token = _esperar_reset_token(context, empleado_id)

    reset = context.api.post(
        "/auth/reset-password",
        json={"token": reset_token, "nuevaPassword": password_activacion},
    )
    assert reset.status_code == 200, (
        f"POST /auth/reset-password devolvió {reset.status_code} al activar "
        f"{empleado_id!r}; se esperaba 200. Cuerpo (recorte): {reset.text[:500]!r}"
    )

    # Login limpio: /auth/login es público en el gateway, sin Bearer heredado.
    context.api.set_token(None)
    login = context.api.post(
        "/auth/login", json={"email": email, "password": password_activacion}
    )
    assert login.status_code == 200, (
        f"POST /auth/login (USER sintético) devolvió {login.status_code} para "
        f"{email!r}; se esperaba 200. Cuerpo (recorte): {login.text[:500]!r}"
    )

    token = _token_de_respuesta(login, "POST /auth/login (USER sintético)")
    context.tokens["user"] = token
    context.token = token
    context.api.set_token(token)
