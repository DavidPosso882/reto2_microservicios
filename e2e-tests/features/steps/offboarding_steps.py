"""Pasos del feature de offboarding (Reto 6, Punto 5).

Flujo real contra el gateway
----------------------------
1. ``DELETE /empleados/{id}`` (ADMIN) hace la baja lógica: el empleado pasa a
   ``RETIRADO`` con ``fechaRetiro`` y empleados-service publica
   ``empleado.retirado`` -> **200** con el empleado retirado.
2. De forma asíncrona: notificaciones-service persiste la notificación
   ``DESVINCULACION`` y auth-service consume el mismo evento, pasa la cuenta
   a ``DESACTIVADA_PERMANENTE`` y publica ``cuenta.desactivada`` (motivo
   RETIRO, ``permanente=true``) -> notificación ``CUENTA``.
3. El retirado queda bloqueado para siempre: login **401**, recover-password
   no emite token nuevo y un reset token viejo responde **401**.
4. Auditoría: ``GET /empleados?estado=RETIRADO`` conserva al empleado con su
   fecha de retiro (la baja es lógica, nunca se borra).

Polling negativo (cómo se distingue "todavía no" de "nunca")
------------------------------------------------------------
* ``eventualmente el empleado retirado no puede iniciar sesión`` sondea el
  login hasta el **401** con timeout explícito. Si vence devolviendo 200, el
  diagnóstico señala que el evento de retiro no fue procesado: la cuenta
  seguía ACTIVA dentro del presupuesto.
* ``sigue sin poder iniciar sesión durante la ventana de observación``
  completa la parte de "permanente": durante
  ``E2E_P5_VENTANA_NEGATIVA_S`` segundos se muestrea el login varias veces;
  cualquier 200 falla al instante y, si nunca ocurre, la ausencia queda
  evidenciada por la ventana agotada (no por un ``sleep`` suelto).
* ``la recuperación no emite un token nuevo`` fotografía las notificaciones
  SEGURIDAD antes de ``POST /auth/recover-password`` y comprueba que no
  aparece ninguna nueva durante la ventana. Si apareciera, el escenario
  falla con el token inesperado.

Independencia
-------------
Cada escenario crea su propio empleado ``E2E-P5-<run_id>`` en el
Antecedentes (mismo paso reutilizado que vacaciones); no comparte datos con
otros escenarios y solo reutiliza el departamento ``E2E-P5-DEPT``.
"""

from __future__ import annotations

import requests
from behave import then, when

from support import config
from support.polling import TimeoutException, esperar_hasta_que


def _requerir_empleado_activo(context):
    """Falla temprano si el Antecedentes no creó el empleado del P5."""
    assert context.active_employee_id, (
        "No hay empleado activo en el escenario; el Antecedentes debe ejecutar "
        "`Y que existe un empleado activo con credenciales establecidas`."
    )


def _usar_token_admin(context):
    """Asegura que la sesión del escenario use el Bearer ADMIN."""
    token = context.tokens.get("admin")
    assert token, (
        "No hay token ADMIN en el escenario; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"`.'
    )
    context.api.set_token(token)


def _login_directo(context, email, password):
    """``POST /auth/login`` fuera de la sesión del escenario (ruta pública)."""
    return requests.post(
        f"{context.base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=config.http_timeout(),
    )


def _notificaciones(context):
    """Lista las notificaciones del empleado activo (requiere ADMIN)."""
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    respuesta = context.api.get(f"/notificaciones/{context.active_employee_id}")
    if respuesta.status_code != 200:
        raise AssertionError(
            f"GET /notificaciones/{context.active_employee_id!r} devolvió "
            f"{respuesta.status_code}; no se puede verificar la evidencia. "
            f"Cuerpo (recorte): {respuesta.text[:300]!r}"
        )
    return respuesta.json()


def _esperar_notificacion(context, predicado, descripcion):
    """Espera una notificación del empleado activo que cumpla ``predicado``.

    Mismo patrón que los puntos 4 y 5 (éxito temprano + reintentos cada 2 s,
    ~30 s); el diagnóstico agrega el último código HTTP si se agota.
    """
    ultimo_estado = {"codigo": None}

    def condicion():
        _usar_token_admin(context)
        respuesta = context.api.get(f"/notificaciones/{context.active_employee_id}")
        ultimo_estado["codigo"] = respuesta.status_code
        if respuesta.status_code != 200:
            return None
        for notificacion in respuesta.json():
            if predicado(notificacion):
                return notificacion
        return None

    try:
        return esperar_hasta_que(condicion, descripcion=descripcion)
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} Último GET /notificaciones/{context.active_employee_id!r}: "
            f"HTTP {ultimo_estado['codigo']}. ¿Están los consumidores de "
            "RabbitMQ procesando empleado.retirado y cuenta.desactivada?"
        ) from exc


# ── Baja lógica y evidencia asíncrona ────────────────────────────────────────


@when("retiro al empleado activo")
def step_retirar_empleado_activo(context):
    """``DELETE /empleados/{id}`` (ADMIN): baja lógica del empleado del P5."""
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    context.last_response = context.api.delete(
        f"/empleados/{context.active_employee_id}"
    )


@then("la respuesta confirma la desvinculación con fecha de retiro")
def step_respuesta_confirma_desvinculacion(context):
    """El 200 del DELETE devuelve el empleado RETIRADO con ``fechaRetiro``."""
    respuesta = context.last_response
    assert respuesta is not None and respuesta.status_code == 200, (
        "La última respuesta no es el 200 de la baja lógica "
        f"(código: {getattr(respuesta, 'status_code', None)})."
    )
    cuerpo = respuesta.json()
    assert cuerpo.get("id") == context.active_employee_id, (
        f"El DELETE afectó a otro empleado: {cuerpo!r}"
    )
    assert cuerpo.get("estado") == "RETIRADO", (
        f"El empleado no quedó RETIRADO: {cuerpo!r}"
    )
    assert cuerpo.get("fechaRetiro"), (
        "La baja lógica no registró fechaRetiro (la auditoría la necesita): "
        f"{cuerpo!r}"
    )


@then("eventualmente llega la notificación de desvinculación al email del empleado")
def step_notificacion_desvinculacion(context):
    """Espera la notificación DESVINCULACION de ``empleado.retirado``."""

    def es_desvinculacion(notificacion):
        mensaje = notificacion.get("mensaje", "")
        return (
            notificacion.get("tipo") == "DESVINCULACION"
            and notificacion.get("destinatario") == context.active_employee_email
            and "vínculo" in mensaje
            and "finalizado" in mensaje
        )

    notificacion = _esperar_notificacion(
        context,
        es_desvinculacion,
        descripcion=(
            f"la notificación DESVINCULACION de "
            f"{context.active_employee_email!r}"
        ),
    )
    assert notificacion.get("empleadoId") == context.active_employee_id, (
        f"La notificación no referencia al empleado del escenario: {notificacion!r}"
    )


@then("eventualmente la cuenta quedó desactivada permanentemente")
def step_cuenta_desactivada_permanente(context):
    """Espera la notificación CUENTA de la baja permanente (motivo RETIRO).

    Es la evidencia observable de que auth-service consumió
    ``empleado.retirado`` y persistió ``DESACTIVADA_PERMANENTE``; sirve como
    sincronización antes de probar recover-password o el reset del token.
    """

    def es_baja_permanente(notificacion):
        mensaje = notificacion.get("mensaje", "")
        return (
            notificacion.get("tipo") == "CUENTA"
            and notificacion.get("destinatario") == context.active_employee_email
            and "desactivada en forma permanente" in mensaje
            and "RETIRO" in mensaje
        )

    _esperar_notificacion(
        context,
        es_baja_permanente,
        descripcion=(
            "la notificación CUENTA de desactivación permanente por retiro"
        ),
    )


# ── Bloqueo de login y ventana negativa ──────────────────────────────────────


@then("eventualmente el empleado retirado no puede iniciar sesión")
def step_eventualmente_retirado_no_entra(context):
    """Polling hasta el 401 del retirado, con timeout explícito.

    La cuenta arranca ACTIVA (el Antecedentes hizo login 200), así que un
    401 solo puede venir del bloqueo por retiro. Si el presupuesto vence con
    200, el diagnóstico indica que ``empleado.retirado`` aún no fue procesado
    por auth-service: no se confunde "todavía" con "nunca" ni se aprueba en
    falso.
    """
    _requerir_empleado_activo(context)
    email = context.active_employee_email
    password = context.active_employee_password
    ultimo = {"codigo": None}
    timeout = 30.0

    def condicion():
        respuesta = _login_directo(context, email, password)
        ultimo["codigo"] = respuesta.status_code
        return respuesta.status_code == 401

    try:
        esperar_hasta_que(
            condicion,
            descripcion=(
                "el bloqueo de login del empleado retirado (HTTP 401)"
            ),
            max_intentos=100000,
            intervalo_ms=config.p5_login_interval_ms(),
            timeout_s=timeout,
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} El login siguió devolviendo {ultimo['codigo']} (cuenta "
            f"aún ACTIVA) durante {timeout:.0f}s después del DELETE "
            "/empleados. ¿auth-service consumió empleado.retirado?"
        ) from exc


@then("el empleado retirado sigue sin poder iniciar sesión")
def step_retirado_sigue_sin_entrar(context):
    """Comprobación puntual posterior: el retirado sigue en 401."""
    _requerir_empleado_activo(context)
    respuesta = _login_directo(
        context,
        context.active_employee_email,
        context.active_employee_password,
    )
    assert respuesta.status_code == 401, (
        "El empleado retirado pudo iniciar sesión de nuevo "
        f"(HTTP {respuesta.status_code}); la baja debe ser permanente. "
        f"Cuerpo (recorte): {respuesta.text[:300]!r}"
    )


@then(
    "el empleado retirado sigue sin poder iniciar sesión durante la ventana "
    "de observación"
)
def step_retirado_401_constante(context):
    """Ventana negativa: el 401 se mantiene durante ``VENTANA_NEGATIVA_S``.

    La condición del polling devuelve verdadero solo si aparece un 200 (fin
    indebido de la baja); agotar la ventana sin un 200 es el éxito, así que
    se reutiliza ``esperar_hasta_que`` y la ``TimeoutException`` se
    interpreta como ausencia confirmada dentro del presupuesto.
    """
    _requerir_empleado_activo(context)
    email = context.active_employee_email
    password = context.active_employee_password
    ventana = config.p5_ventana_negativa_s()
    intentos = max(2, int(ventana / 2) + 1)

    def se_reactivo_indebidamente():
        respuesta = _login_directo(context, email, password)
        return respuesta.status_code == 200

    try:
        esperar_hasta_que(
            se_reactivo_indebidamente,
            descripcion=(
                "una reactivación indebida del empleado retirado (login 200)"
            ),
            max_intentos=intentos,
            intervalo_ms=2000,
            timeout_s=ventana,
        )
    except TimeoutException:
        return  # nunca volvió a entrar durante la ventana: bloqueo permanente

    raise AssertionError(
        "El empleado retirado volvió a iniciar sesión (HTTP 200) dentro de la "
        f"ventana de observación de {ventana:.0f}s; la baja debe ser "
        "permanente."
    )


# ── Recuperación de contraseña del retirado ──────────────────────────────────


@when("el empleado retirado intenta recuperar su contraseña")
def step_retirado_intenta_recuperar(context):
    """``POST /auth/recover-password`` del retirado (respuesta anti-enumeración).

    Antes de llamar, fotografía los ids de las notificaciones SEGURIDAD ya
    emitidas: el paso siguiente comprueba que la llamada no agrega ninguna
    (un retirado no debe recibir un token de recuperación nuevo).
    """
    _requerir_empleado_activo(context)
    context.security_notifications_snapshot = [
        notificacion["id"]
        for notificacion in _notificaciones(context)
        if notificacion.get("tipo") == "SEGURIDAD"
    ]
    context.last_response = requests.post(
        f"{context.base_url}/auth/recover-password",
        json={"email": context.active_employee_email},
        timeout=config.http_timeout(),
    )


@then("la respuesta de recuperación es uniforme")
def step_respuesta_recuperacion_uniforme(context):
    """La API responde 200 uniforme sin revelar que la cuenta está desactivada."""
    respuesta = context.last_response
    assert respuesta is not None and respuesta.status_code == 200, (
        "POST /auth/recover-password no devolvió el 200 uniforme esperado "
        f"(código: {getattr(respuesta, 'status_code', None)})."
    )
    cuerpo = respuesta.json()
    assert cuerpo.get("enviado") is True, (
        f"La respuesta de recuperación no es la uniforme esperada: {cuerpo!r}"
    )
    assert cuerpo.get("message"), (
        "La respuesta uniforme no acompaña un mensaje genérico: "
        f"{cuerpo!r}"
    )


@then("la recuperación no emite un token nuevo")
def step_recuperacion_sin_token_nuevo(context):
    """Ventana negativa: no aparece ninguna notificación SEGURIDAD nueva.

    La condición devuelve la lista de notificaciones SEGURIDAD que no estaban
    en la foto previa; si aparece alguna, el escenario falla con ella. Si la
    ventana se agota sin novedades, la ausencia de token queda evidenciada
    dentro del presupuesto.
    """
    snapshot = set(context.security_notifications_snapshot or [])
    ventana = config.p5_ventana_negativa_s()
    intentos = max(2, int(ventana / 2) + 1)

    def token_nuevo():
        nuevas = [
            notificacion
            for notificacion in _notificaciones(context)
            if notificacion.get("tipo") == "SEGURIDAD"
            and notificacion.get("id") not in snapshot
        ]
        return nuevas or None

    try:
        nuevas = esperar_hasta_que(
            token_nuevo,
            descripcion=(
                "un token de recuperación nuevo para el empleado retirado"
            ),
            max_intentos=intentos,
            intervalo_ms=2000,
            timeout_s=ventana,
        )
    except TimeoutException:
        return  # no apareció ningún token dentro de la ventana

    raise AssertionError(
        "recover-password emitió un token nuevo para un empleado retirado "
        f"(notificaciones SEGURIDAD: {nuevas!r}). La cuenta está "
        "DESACTIVADA_PERMANENTE y no debe poder recuperar su contraseña."
    )


@then("el token de activación anterior ya no sirve")
def step_token_anterior_rechazado(context):
    """``POST /auth/reset-password`` con el token previo al retiro -> 401."""
    _requerir_empleado_activo(context)
    assert context.active_employee_reset_token, (
        "No hay reset token del empleado activo en el contexto; el "
        "Antecedentes debió guardarlo al activar la cuenta."
    )
    respuesta = requests.post(
        f"{context.base_url}/auth/reset-password",
        json={
            "token": context.active_employee_reset_token,
            "nuevaPassword": config.user_activation_password(),
        },
        timeout=config.http_timeout(),
    )
    context.last_response = respuesta
    assert respuesta.status_code == 401, (
        "Un token de activación anterior al retiro reactivó la cuenta "
        f"(HTTP {respuesta.status_code}); se esperaba 401. "
        f"Cuerpo (recorte): {respuesta.text[:300]!r}"
    )
    error = str(respuesta.json().get("error", ""))
    assert "token" in error.lower(), (
        f"El 401 no explica el rechazo del token: {error!r}"
    )


# ── Auditoría ────────────────────────────────────────────────────────────────


@when('consulto los empleados con estado "{estado}"')
def step_consultar_empleados_por_estado(context, estado):
    """``GET /empleados?estado=...`` con el Bearer ADMIN."""
    _usar_token_admin(context)
    context.last_response = context.api.get(
        "/empleados", params={"estado": estado}
    )


@then("la lista de auditoría incluye al empleado retirado con su fecha de retiro")
def step_auditoria_incluye_retirado(context):
    """La baja lógica conserva al empleado en la consulta de auditoría."""
    respuesta = context.last_response
    assert respuesta is not None and respuesta.status_code == 200, (
        "GET /empleados?estado=RETIRADO no devolvió 200 "
        f"(código: {getattr(respuesta, 'status_code', None)})."
    )
    cuerpo = respuesta.json()
    assert isinstance(cuerpo, list), (
        f"La auditoría no devolvió una lista de empleados: {cuerpo!r}"
    )
    encontrado = next(
        (empleado for empleado in cuerpo if empleado.get("id") == context.active_employee_id),
        None,
    )
    assert encontrado is not None, (
        f"El empleado retirado {context.active_employee_id!r} no aparece en "
        f"GET /empleados?estado=RETIRADO (total: {len(cuerpo)})."
    )
    assert encontrado.get("estado") == "RETIRADO", (
        f"El registro de auditoría no está RETIRADO: {encontrado!r}"
    )
    assert encontrado.get("fechaRetiro"), (
        f"El registro de auditoría no conserva fechaRetiro: {encontrado!r}"
    )
