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

Cómo se obtiene un empleado activo con credenciales (Reto 6, Punto 5)
--------------------------------------------------------------------
El paso ``Dado que existe un empleado activo con credenciales establecidas``
reutiliza el mismo camino real que el P3/P4 (alta ADMIN, notificación
SEGURIDAD de ``usuario.creado``, reset con el token y login 200), pero crea
un empleado ``E2E-P5-<run_id>`` en el departamento ``E2E-P5-DEPT`` y deja la
sesión del escenario como ADMIN. Es la precondición compleja que comparten
los features de vacaciones y de offboarding, sin depender de otros
escenarios.

Credenciales (nunca en los ``.feature``)
----------------------------------------
* ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` para el rol ``"admin"``.
* ``USER_EMAIL`` / ``USER_PASSWORD`` para el rol ``"user"`` (cuentas ya
  existentes en el entorno).
* ``E2E_USER_PASSWORD`` (default ``User1234``) para las cuentas sintéticas
  que activan los puntos 3 y 5.

Si faltan, el escenario falla con un mensaje que indica la variable esperada.
"""

from __future__ import annotations

import re

from behave import given

from support import config
from support.polling import TimeoutException, esperar_hasta_que

# El mensaje de la notificación incluye el JWT de reset en prosa; se extraen
# sus tres segmentos base64url (header.payload.firma).
_RESET_TOKEN_RE = re.compile(r"([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def _esperar_reset_token(context, empleado_id):
    """Espera a que llegue la notificación de activación y extrae el token.

    Reutiliza el helper de polling del Punto 4 (``esperar_hasta_que``): evalúa
    de inmediato y reintenta cada 2 s hasta ~30 s. El flujo de negocio del
    Punto 3 es síncrono; lo asíncrono es la creación de la cuenta por
    RabbitMQ y su notificación. Devuelve el token o falla con diagnóstico si
    se agota el presupuesto.
    """
    ultimo_estado = {"codigo": None}

    def condicion():
        respuesta = context.api.get(f"/notificaciones/{empleado_id}")
        ultimo_estado["codigo"] = respuesta.status_code
        if respuesta.status_code != 200:
            return None
        for notificacion in respuesta.json():
            coincidencia = _RESET_TOKEN_RE.search(notificacion.get("mensaje", ""))
            if coincidencia:
                return coincidencia.group(1)
        return None

    try:
        return esperar_hasta_que(
            condicion,
            descripcion=(
                f"la notificación con el token de activación de {empleado_id!r}"
            ),
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} Último GET /notificaciones/{empleado_id!r}: "
            f"HTTP {ultimo_estado['codigo']}. ¿Está auth-service consumiendo "
            "empleado.creado y el consumer de notificaciones levantado?"
        ) from exc


def _token_de_respuesta(respuesta, contexto):
    """Extrae el access token del login aceptando ``accessToken`` o ``token``."""
    payload = respuesta.json()
    token = payload.get("accessToken") or payload.get("token")
    assert token, (
        f"{contexto} respondió 200 pero sin token utilizable "
        f"(claves: {sorted(payload)!r})."
    )
    return token


def _registrar_empleado(context, *, empleado_id, email, numero_empleado, departamento_id, etiqueta):
    """POST /empleados (ADMIN) con el payload canónico de una cuenta E2E."""
    return context.api.post(
        "/empleados",
        json={
            "id": empleado_id,
            "nombre": etiqueta,
            "apellido": "E2E",
            "email": email,
            "numeroEmpleado": numero_empleado,
            "cargo": "QA",
            "area": "Tecnología",
            "departamentoId": departamento_id,
            "fechaIngreso": "2026-01-15",
            "estado": "ACTIVO",
        },
    )


def _activar_cuenta(context, *, empleado_id, email, password, departamento_id, etiqueta):
    """Alta + activación real + login; devuelve ``(access_token, reset_token)``.

    Reproduce el camino completo del P3/P4 con endpoints reales y polling:

    1. ``POST /empleados`` (201) con el Bearer ADMIN vigente.
    2. Espera la notificación SEGURIDAD (``usuario.creado``) y extrae el
       token de activación del mensaje.
    3. ``POST /auth/reset-password`` (200) para fijar la contraseña.
    4. ``POST /auth/login`` (200) y devuelve el access token.

    Requiere que el Bearer ADMIN ya esté aplicado en la sesión del escenario.
    """
    alta = _registrar_empleado(
        context,
        empleado_id=empleado_id,
        email=email,
        numero_empleado=f"EMP-{empleado_id}",
        departamento_id=departamento_id,
        etiqueta=etiqueta,
    )
    assert alta.status_code == 201, (
        f"POST /empleados (ADMIN) devolvió {alta.status_code} al crear "
        f"{empleado_id!r}; se esperaba 201. Cuerpo (recorte): {alta.text[:500]!r}"
    )

    reset_token = _esperar_reset_token(context, empleado_id)

    reset = context.api.post(
        "/auth/reset-password",
        json={"token": reset_token, "nuevaPassword": password},
    )
    assert reset.status_code == 200, (
        f"POST /auth/reset-password devolvió {reset.status_code} al activar "
        f"{empleado_id!r}; se esperaba 200. Cuerpo (recorte): {reset.text[:500]!r}"
    )

    # Login limpio: /auth/login es público en el gateway, sin Bearer heredado.
    context.api.set_token(None)
    login = context.api.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, (
        f"POST /auth/login (cuenta sintética) devolvió {login.status_code} para "
        f"{email!r}; se esperaba 200. Cuerpo (recorte): {login.text[:500]!r}"
    )

    return _token_de_respuesta(login, "POST /auth/login (USER sintético)"), reset_token


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

    token, _reset_token = _activar_cuenta(
        context,
        empleado_id=empleado_id,
        email=email,
        password=password_activacion,
        departamento_id=config.E2E_DEPARTMENT_ID,
        etiqueta="Usuario",
    )
    context.tokens["user"] = token
    context.token = token
    context.api.set_token(token)


@given("que existe un empleado activo con credenciales establecidas")
def step_empleado_activo_con_credenciales(context):
    """Precondición compleja del Punto 5: empleado + credenciales activas.

    Crea desde cero un empleado único ``E2E-P5-<run_id>`` en el departamento
    ``E2E-P5-DEPT`` (asegurado antes por el paso reutilizado del P3),
    espera con polling el token de activación de la notificación SEGURIDAD,
    establece la contraseña y confirma el login 200. Guarda en el contexto
    los datos del empleado activo y su reset token (usado después por el
    escenario de offboarding) y deja la sesión como ADMIN para el resto del
    escenario.

    Requiere el Bearer ADMIN del Antecedentes: la ruta ``POST /empleados``
    está restringida a ese rol.
    """
    admin_token = context.tokens.get("admin")
    assert admin_token, (
        "No hay token ADMIN en el escenario; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"` antes de crear el empleado activo.'
    )
    context.api.set_token(admin_token)

    run_id = context.run_id
    empleado_id = f"E2E-P5-{run_id}"
    email = f"e2e-p5-{run_id}@empresa.com"
    password = config.user_activation_password()
    context.active_employee_id = empleado_id
    context.active_employee_email = email
    context.active_employee_password = password

    token, reset_token = _activar_cuenta(
        context,
        empleado_id=empleado_id,
        email=email,
        password=password,
        departamento_id=config.E2E_P5_DEPARTMENT_ID,
        etiqueta="Activo",
    )
    context.active_employee_reset_token = reset_token
    context.tokens["user"] = token

    # El escenario continúa operando como ADMIN (vacaciones y offboarding lo
    # necesitan); el token USER queda guardado por si un paso lo pidiera.
    context.token = admin_token
    context.api.set_token(admin_token)
