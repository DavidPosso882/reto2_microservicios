"""Pasos del feature de onboarding asíncrono (Reto 6, Punto 4).

Flujo real contra el gateway (``http://localhost:8080``), sin esperas fijas:

1. ``POST /empleados`` (ADMIN) da de alta un empleado único
   ``E2E-P4-<run_id>`` y responde **201** de forma síncrona.
2. En segundo plano, ``empleado.creado`` viaja por RabbitMQ. auth-service
   persiste la cuenta USER en estado ``SUSPENDIDA_TEMPORAL`` y publica
   ``usuario.creado`` con el token de activación; notificaciones-service
   persiste el envío simulado (``BIENVENIDA`` desde el evento del empleado y
   ``SEGURIDAD`` desde el evento de auth).
3. Los pasos ``eventualmente ...`` esperan esos eventos con
   :func:`support.polling.esperar_hasta_que` (éxito temprano + reintentos), y
   fallan con diagnóstico si se agota el presupuesto de ~30 s.
4. El token de la notificación SEGURIDAD es el que ``POST
   /auth/reset-password`` consume para que el empleado establezca su password;
   después ``POST /auth/login`` responde **200** con un access token real.

Cómo se prueba que "auth creó el usuario"
-----------------------------------------
auth-service no expone lectura de usuarios: su API solo tiene login, reset,
recuperación y bootstrap. La evidencia observable de que la cuenta existe es
la notificación ``SEGURIDAD`` publicada por ``usuario.creado``: ese evento se
emite (con el reset token) inmediatamente después de persistir la cuenta en
``aplicarEmpleadoCreado``. El empleado es único por escenario, así que la
notificación con ``empleadoId`` + ``destinatario`` del escenario no puede
venir de ningún otro alta.

Independencia
-------------
Cada escenario registra su propio empleado con ``context.run_id`` (uuid4 por
escenario, ver ``environment.py``); el único estado compartido es el
departamento ``E2E-P4-DEPT``, creado de forma idempotente en el Antecedentes
con el paso reutilizado del Punto 3.
"""

from __future__ import annotations

import re

from behave import then, when

from support import config
from support.polling import TimeoutException, esperar_hasta_que

# El mensaje de la notificación SEGURIDAD incluye el JWT de reset en prosa; se
# extraen sus tres segmentos base64url (header.payload.firma). Se repite el
# patrón de auth_steps a propósito: los módulos de steps se cargan con
# ``exec_file`` (no se importan entre sí), importar otro módulo de steps
# duplicaría el registro de sus pasos.
_RESET_TOKEN_RE = re.compile(r"([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def _requerir_empleado_onboarding(context):
    """Falla temprano si el escenario todavía no registró su empleado."""
    assert context.onboarding_employee_id, (
        "No hay empleado de onboarding en el escenario; ejecutá antes "
        '`Cuando registro el empleado de onboarding "E2E-P4"`.'
    )


def _empleado_onboarding(context, prefijo):
    """Payload canónico de un empleado del Punto 4, único por escenario."""
    sufijo = context.run_id
    return {
        "id": f"{prefijo}-{sufijo}",
        "nombre": "Onboarding",
        "apellido": "E2E",
        "email": f"{prefijo.lower()}-{sufijo}@empresa.com",
        "numeroEmpleado": f"EMP-{prefijo}-{sufijo}",
        "cargo": "QA",
        "area": "Tecnología",
        "departamentoId": config.E2E_P4_DEPARTMENT_ID,
        "fechaIngreso": "2026-01-15",
        "estado": "ACTIVO",
    }


def _esperar_notificacion(context, tipo, descripcion):
    """Espera una notificación del empleado por tipo y destinatario.

    Sondea ``GET /notificaciones/{empleadoId}`` con ``esperar_hasta_que``
    (éxito temprano, reintentos cada 2 s, presupuesto ~30 s) y devuelve la
    primera notificación que coincida. Si se agota, agrega al diagnóstico el
    último código HTTP observado.
    """
    empleado_id = context.onboarding_employee_id
    email = context.onboarding_email
    ultimo_estado = {"codigo": None}

    def condicion():
        respuesta = context.api.get(f"/notificaciones/{empleado_id}")
        ultimo_estado["codigo"] = respuesta.status_code
        if respuesta.status_code != 200:
            return None
        for notificacion in respuesta.json():
            if (
                notificacion.get("tipo") == tipo
                and notificacion.get("destinatario") == email
            ):
                return notificacion
        return None

    try:
        return esperar_hasta_que(condicion, descripcion=descripcion)
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} Último GET /notificaciones/{empleado_id!r}: "
            f"HTTP {ultimo_estado['codigo']}. ¿Están los servicios "
            "consumiendo los eventos por RabbitMQ?"
        ) from exc


@when('registro el empleado de onboarding "{prefijo}"')
def step_registrar_empleado_onboarding(context, prefijo):
    """POST /empleados (ADMIN) con un empleado único del escenario (201)."""
    assert context.tokens.get("admin"), (
        "No hay token ADMIN; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"` antes de registrar.'
    )
    payload = _empleado_onboarding(context, prefijo)
    context.onboarding_employee_id = payload["id"]
    context.onboarding_email = payload["email"]
    context.last_response = context.api.post("/empleados", json=payload)
    assert context.last_response.status_code == 201, (
        f"POST /empleados devolvió {context.last_response.status_code} al "
        f"registrar {payload['id']!r}; se esperaba 201. "
        f"Cuerpo (recorte): {context.last_response.text[:500]!r}"
    )


@when(
    'registro el empleado de onboarding "{prefijo}" '
    "con un departamento inexistente"
)
def step_registrar_empleado_departamento_inexistente(context, prefijo):
    """POST /empleados apuntando a un departamento que no existe.

    Empleados-service valida la referencia antes de persistir; el código real
    observado en el stack levantado es 400 (el feature lo verifica con el paso
    común ``respuesta código 400``).
    """
    assert context.tokens.get("admin"), (
        "No hay token ADMIN; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"` antes de registrar.'
    )
    payload = _empleado_onboarding(context, prefijo)
    payload["departamentoId"] = f"{prefijo}-DEPT-INEXISTENTE-{context.run_id}"
    context.last_response = context.api.post("/empleados", json=payload)


@when(
    'registro el empleado de onboarding "{prefijo}" '
    "con campos obligatorios faltantes"
)
def step_registrar_empleado_campos_faltantes(context, prefijo):
    """POST /empleados sin ``email`` ni ``numeroEmpleado`` (validación 400)."""
    assert context.tokens.get("admin"), (
        "No hay token ADMIN; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"` antes de registrar.'
    )
    payload = _empleado_onboarding(context, prefijo)
    payload["id"] = f"{payload['id']}-FALTANTE"
    payload.pop("email")
    payload.pop("numeroEmpleado")
    context.last_response = context.api.post("/empleados", json=payload)


@then("eventualmente auth creó el usuario para el email del empleado")
def step_eventualmente_auth_creo_usuario(context):
    """Espera la notificación que prueba que auth-service creó la cuenta.

    ``usuario.creado`` se publica justo después de persistir la cuenta; su
    notificación SEGURIDAD (con reset token) es la evidencia observable. Se
    guarda en el contexto para el paso de establecimiento de password.
    """
    _requerir_empleado_onboarding(context)
    notificacion = _esperar_notificacion(
        context,
        "SEGURIDAD",
        descripcion=(
            "la notificación SEGURIDAD (cuenta creada por auth-service) de "
            f"{context.onboarding_email!r}"
        ),
    )
    assert notificacion.get("destinatario") == context.onboarding_email, (
        "La notificación SEGURIDAD no está dirigida al email del escenario: "
        f"{notificacion!r}"
    )
    coincidencia = _RESET_TOKEN_RE.search(notificacion.get("mensaje", ""))
    assert coincidencia, (
        "La notificación SEGURIDAD de auth-service no incluye el token de "
        f"activación: {notificacion.get('mensaje', '')[:300]!r}"
    )
    context.onboarding_security_notification = notificacion


@then("eventualmente llega la notificación de bienvenida al email del empleado")
def step_eventualmente_bienvenida(context):
    """Espera la notificación BIENVENIDA del alta (medio email simulado)."""
    _requerir_empleado_onboarding(context)
    context.onboarding_welcome_notification = _esperar_notificacion(
        context,
        "BIENVENIDA",
        descripcion=(
            f"la notificación BIENVENIDA de {context.onboarding_email!r}"
        ),
    )


@then("la notificación de bienvenida es un correo simulado al email del empleado")
def step_bienvenida_canal_simulado(context):
    """Verifica el contenido del envío simulado: destinatario, empleado y fecha."""
    notificacion = context.onboarding_welcome_notification
    assert notificacion is not None, (
        "No hay notificación de bienvenida en el contexto; ejecutá antes "
        "`Entonces eventualmente llega la notificación de bienvenida al email "
        "del empleado`."
    )
    assert notificacion.get("destinatario") == context.onboarding_email, (
        "El medio email simulado no apunta al email del empleado: "
        f"{notificacion!r}"
    )
    assert notificacion.get("empleadoId") == context.onboarding_employee_id, (
        "La notificación no referencia al empleado del escenario: "
        f"{notificacion!r}"
    )
    assert "bienvenido" in notificacion.get("mensaje", "").lower(), (
        "El mensaje de bienvenida no saluda al empleado: "
        f"{notificacion.get('mensaje', '')[:300]!r}"
    )
    assert notificacion.get("fechaEnvio"), (
        "La notificación de bienvenida no registra fechaEnvio; el medio email "
        "simulado debería dejar traza del envío."
    )


@when("el empleado establece su contraseña con el token de la notificación")
def step_establecer_password(context):
    """Extrae el reset token y activa la cuenta con POST /auth/reset-password."""
    notificacion = context.onboarding_security_notification
    assert notificacion is not None, (
        "No hay notificación SEGURIDAD en el contexto; ejecutá antes "
        "`Entonces eventualmente auth creó el usuario para el email del "
        "empleado`."
    )
    coincidencia = _RESET_TOKEN_RE.search(notificacion.get("mensaje", ""))
    assert coincidencia, (
        "La notificación SEGURIDAD no trae un token de activación extraíble: "
        f"{notificacion.get('mensaje', '')[:300]!r}"
    )

    context.last_response = context.api.post(
        "/auth/reset-password",
        json={
            "token": coincidencia.group(1),
            "nuevaPassword": config.user_activation_password(),
        },
    )
    assert context.last_response.status_code == 200, (
        f"POST /auth/reset-password devolvió {context.last_response.status_code}; "
        f"se esperaba 200. Cuerpo (recorte): {context.last_response.text[:500]!r}"
    )


@then("puede iniciar sesión con la contraseña establecida")
def step_login_password_establecida(context):
    """Login real con la password establecida; guarda el Bearer USER."""
    _requerir_empleado_onboarding(context)
    # /auth/login es público: se quita el Bearer ADMIN heredado del Antecedentes.
    context.api.set_token(None)
    context.last_response = context.api.post(
        "/auth/login",
        json={
            "email": context.onboarding_email,
            "password": config.user_activation_password(),
        },
    )
    assert context.last_response.status_code == 200, (
        f"POST /auth/login devolvió {context.last_response.status_code} para "
        f"{context.onboarding_email!r} tras establecer la password; se "
        f"esperaba 200. Cuerpo (recorte): {context.last_response.text[:500]!r}"
    )

    payload = context.last_response.json()
    token = payload.get("accessToken") or payload.get("token")
    assert token, (
        "POST /auth/login respondió 200 sin access token utilizable "
        f"(claves: {sorted(payload)!r})."
    )
    context.token = token
    context.tokens["user"] = token
    context.api.set_token(token)


@then('su cuenta quedó activa para el rol "USER"')
def step_cuenta_activa_user(context):
    """La respuesta del login confirma rol USER y estado ACTIVA."""
    payload = context.last_response.json() if context.last_response is not None else {}
    usuario = payload.get("usuario") or {}
    assert usuario.get("role") == "USER", (
        f"La cuenta no quedó con rol USER: {usuario!r}"
    )
    assert usuario.get("estado") == "ACTIVA", (
        f"La cuenta no quedó ACTIVA tras el reset: {usuario!r}"
    )
    assert usuario.get("email") == context.onboarding_email, (
        f"La cuenta activa no es la del escenario: {usuario!r}"
    )


@then("la respuesta explica que el departamento no existe")
def step_error_departamento_inexistente(context):
    """El 400 de empleados-service nombra el departamento inexistente."""
    respuesta = context.last_response
    assert respuesta is not None, "No hay respuesta HTTP para inspeccionar."
    cuerpo = respuesta.json()
    error = str(cuerpo.get("error", ""))
    assert "departamento" in error.lower() and "no existe" in error.lower(), (
        "La respuesta no explica que el departamento no existe: "
        f"{cuerpo!r}"
    )


@then("la respuesta lista los campos obligatorios")
def step_error_campos_obligatorios(context):
    """El 400 de validación nombra al menos los campos omitidos por el escenario."""
    respuesta = context.last_response
    assert respuesta is not None, "No hay respuesta HTTP para inspeccionar."
    cuerpo = respuesta.json()
    error = str(cuerpo.get("error", "")).lower()
    assert "email" in error and "numeroempleado" in error, (
        "La respuesta no lista los campos obligatorios faltantes: "
        f"{cuerpo!r}"
    )
