"""Pasos del feature de vacaciones y ciclo de vida de la cuenta (Punto 5).

Qué se verifica contra el stack real
------------------------------------
* ``POST /vacaciones`` (ADMIN) -> **201** con ``estado=PROGRAMADA`` y, de
  forma asíncrona, la notificación ``VACACIONES`` "Tus vacaciones fueron
  programadas desde ... hasta ..." (publicada por ``vacaciones.programadas``
  y persistida por el medio email simulado).
* Rechazo de fechas incoherentes: ``fechaFin`` anterior a ``fechaInicio``
  -> **400** real de vacaciones-service.
* Rechazo de solapamiento: segundo período que se pisa con uno vigente
  -> **400** real, con la clave ``conflicto`` describiendo el período en
  pugna.
* Ciclo completo del Reto 5: un período ``hoy -> hoy`` inicia y finaliza con
  el scheduler; auth-service consume ``vacaciones.iniciadas`` (cuenta
  ``SUSPENDIDA_TEMPORAL`` -> login **401**) y ``vacaciones.finalizadas``
  (cuenta ``ACTIVA`` -> login **200** de nuevo).

Control del tiempo (por qué el escenario del ciclo crea cuentas satélite)
-------------------------------------------------------------------------
El scheduler de vacaciones aplica las dos transiciones del período ``hoy ->
hoy`` en el MISMO tick (comparación inclusiva ``<= hoy`` en ambos extremos,
ver ``vacaciones/app/scheduler.rb``), así que para una sola cuenta la ventana
de ``SUSPENDIDA_TEMPORAL`` es de pocos milisegundos y un polling HTTP no
puede observarla de forma determinista. El escenario no toca la frecuencia
del scheduler (``SCHEDULER_INTERVAL_S``, default 60 s) ni depende de ella
para aprobar: espera con polling hasta ~75 s a que ocurra el tick. Para que
la suspensión sea observable, el paso del ciclo crea ``E2E_P5_SENUELOS``
cuentas satélite con su propio período ``hoy -> hoy`` y las programa
inmediatamente después del empleado protagonista: todas transicionan en el
mismo tick y auth-service las procesa en serie, estirando la ventana del
protagonista a unos cientos de milisegundos (medido: ~365 ms con 6+1
cuentas). Todo se hace por HTTP público, sin SQL ni broker.

Los satélite solo necesitan existir como cuentas (la notificación SEGURIDAD
prueba que auth-service las creó); no se activan con contraseña porque no se
hace login con ellas.

Polling negativo
----------------
El paso ``eventualmente el empleado no puede iniciar sesión`` sondea el login
hasta ver **401** con un timeout explícito. Si el presupuesto se agota
sigue devolviendo 200 (cuenta ACTIVA): el diagnóstico distingue "el evento
aún no fue procesado" de "el tick cayó mal" y el escenario falla en vez de
quedar en verde por accidente. La reactivación usa un presupuesto corto
ocurre en el mismo tick, apenas después del 401.

Independencia
-------------
Cada escenario usa ``context.run_id`` (uuid4) en el empleado protagonista
(``E2E-P5-<run_id>``) y en los satélite (``E2E-P5-SENUELO-<run_id>-<n>``);
el único estado compartido es el departamento ``E2E-P5-DEPT``, asegurado de
forma idempotente por el Antecedentes con el paso reutilizado del P3.
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
    """``POST /auth/login`` fuera de la sesión del escenario.

    ``/auth/login`` es público; se usa una petición directa para que el
    polling del ciclo no altere el Bearer ADMIN que el escenario mantiene en
    ``context.api``.
    """
    return requests.post(
        f"{context.base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=config.http_timeout(),
    )


def _post_vacacion(context, *, empleado_id, fecha_inicio, fecha_fin, descripcion):
    """Programa un período y devuelve la respuesta real (201 o rechazo).

    El evento ``empleado.creado`` viaja por RabbitMQ hasta la réplica local de
    vacaciones-service; si el POST llega antes, el servicio responde 400 con
    "no existe en la réplica local". Ese caso se reintenta con polling (es
    propagación, no un rechazo de negocio); cualquier otro código se devuelve
    tal cual para que los pasos verifiquen el rechazo real (400 de rango,
    400 de solapamiento, etc.).
    """
    payload = {
        "empleadoId": empleado_id,
        "fechaInicio": fecha_inicio,
        "fechaFin": fecha_fin,
    }
    ultimo = {"codigo": None, "cuerpo": None}

    def condicion():
        respuesta = context.api.post("/vacaciones", json=payload)
        ultimo["codigo"] = respuesta.status_code
        ultimo["cuerpo"] = respuesta.text[:300]
        if respuesta.status_code == 400 and "réplica local" in respuesta.text:
            return None
        # Respuesta 201 o rechazo de negocio: detener y devolverla envuelta
        # (requests.Response es falsy para 4xx, así que no puede ser el
        # valor truthy que espera el polling).
        return {"respuesta": respuesta}

    try:
        return esperar_hasta_que(
            condicion,
            descripcion=f"la programación de {descripcion}",
            max_intentos=15,
            intervalo_ms=1000,
            timeout_s=15.0,
        )["respuesta"]
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} Último POST /vacaciones: HTTP {ultimo['codigo']} "
            f"(cuerpo recortado: {ultimo['cuerpo']!r}). ¿Llegó el evento "
            "empleado.creado a la réplica local de vacaciones-service?"
        ) from exc


def _esperar_notificacion(context, predicado, descripcion):
    """Espera una notificación del empleado activo que cumpla ``predicado``.

    Mismo patrón que el P4 (éxito temprano + reintentos cada 2 s, ~30 s):
    sondea ``GET /notificaciones/{empleadoId}`` y devuelve la primera
    notificación que el predicado acepte. El diagnóstico agrega el último
    código HTTP si se agota el presupuesto.
    """
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    empleado_id = context.active_employee_id
    ultimo_estado = {"codigo": None}

    def condicion():
        respuesta = context.api.get(f"/notificaciones/{empleado_id}")
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
            f"{exc} Último GET /notificaciones/{empleado_id!r}: "
            f"HTTP {ultimo_estado['codigo']}. ¿Están los consumidores de "
            "RabbitMQ procesando vacaciones.programadas y los eventos de "
            "cuenta?"
        ) from exc


# ── Programación exitosa ─────────────────────────────────────────────────────


@when("programo un período de vacaciones futuro")
def step_programar_periodo_futuro(context):
    """Programa un período válido a futuro (hoy+10 -> hoy+14) como ADMIN."""
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    inicio = config.fecha_utc(10)
    fin = config.fecha_utc(14)
    context.vacation_period_dates = (inicio, fin)
    context.last_response = _post_vacacion(
        context,
        empleado_id=context.active_employee_id,
        fecha_inicio=inicio,
        fecha_fin=fin,
        descripcion="un período futuro válido",
    )
    if context.last_response.status_code == 201:
        context.vacation_period_id = context.last_response.json().get("id")


@then("la respuesta confirma el período programado")
def step_respuesta_confirma_periodo(context):
    """El 201 devuelve el período PROGRAMADA con los datos del escenario."""
    respuesta = context.last_response
    assert respuesta is not None and respuesta.status_code == 201, (
        "La última respuesta no es el 201 de la programación "
        f"(código: {getattr(respuesta, 'status_code', None)})."
    )
    cuerpo = respuesta.json()
    inicio, fin = context.vacation_period_dates
    assert cuerpo.get("id") == context.vacation_period_id and cuerpo.get("id"), (
        f"El POST devolvió el id {cuerpo.get('id')!r}; no es utilizable."
    )
    assert cuerpo.get("empleadoId") == context.active_employee_id, (
        f"El período no es del empleado del escenario: {cuerpo!r}"
    )
    assert cuerpo.get("estado") == "PROGRAMADA", (
        f"El período no quedó PROGRAMADA: {cuerpo!r}"
    )
    assert (cuerpo.get("fechaInicio"), cuerpo.get("fechaFin")) == (inicio, fin), (
        f"El período no conserva las fechas pedidas ({inicio} -> {fin}): {cuerpo!r}"
    )
    context.vacation_period_id = cuerpo["id"]


@then("eventualmente llega la notificación de vacaciones programadas")
def step_notificacion_vacaciones_programadas(context):
    """Espera la notificación VACACIONES de ``vacaciones.programadas``."""
    inicio, fin = context.vacation_period_dates
    email = context.active_employee_email

    def es_la_confirmacion(notificacion):
        mensaje = notificacion.get("mensaje", "")
        return (
            notificacion.get("tipo") == "VACACIONES"
            and notificacion.get("destinatario") == email
            and "fueron programadas" in mensaje
            and f"desde {inicio} hasta {fin}" in mensaje
        )

    notificacion = _esperar_notificacion(
        context,
        es_la_confirmacion,
        descripcion=(
            f"la notificación VACACIONES de {email!r} con el período "
            f"{inicio} -> {fin}"
        ),
    )
    assert notificacion.get("empleadoId") == context.active_employee_id, (
        f"La notificación no referencia al empleado del escenario: {notificacion!r}"
    )
    assert notificacion.get("fechaEnvio"), (
        "La notificación de vacaciones no registra fechaEnvio; el medio email "
        "simulado debería dejar traza del envío."
    )


# ── Rechazos síncronos ───────────────────────────────────────────────────────


@when("programo un período de vacaciones con fechaFin anterior a fechaInicio")
def step_programar_fechas_incoherentes(context):
    """POST con ``fechaFin`` anterior a ``fechaInicio`` (validación 400)."""
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    inicio = config.fecha_utc(5)
    fin = config.fecha_utc(2)
    context.vacation_period_dates = (inicio, fin)
    context.last_response = _post_vacacion(
        context,
        empleado_id=context.active_employee_id,
        fecha_inicio=inicio,
        fecha_fin=fin,
        descripcion="un período con fechas incoherentes",
    )


@then("la respuesta explica que fechaFin no puede ser anterior a fechaInicio")
def step_error_fechas_incoherentes(context):
    """El 400 real nombra ``fechaFin`` y su relación con ``fechaInicio``."""
    respuesta = context.last_response
    assert respuesta is not None, "No hay respuesta HTTP para inspeccionar."
    error = str(respuesta.json().get("error", ""))
    assert "fechaFin" in error and "posterior a fechaInicio" in error, (
        "La respuesta no explica que fechaFin debe ser igual o posterior a "
        f"fechaInicio: {error!r}"
    )


@when("programo otro período de vacaciones que se solapa con el anterior")
def step_programar_periodo_solapado(context):
    """Segundo POST que pisa el período vigente del escenario (validación)."""
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    inicio = config.fecha_utc(12)
    fin = config.fecha_utc(16)
    context.last_response = _post_vacacion(
        context,
        empleado_id=context.active_employee_id,
        fecha_inicio=inicio,
        fecha_fin=fin,
        descripcion="un período solapado",
    )


@then("la respuesta incluye el período en conflicto")
def step_error_solapamiento(context):
    """El 400 trae ``conflicto`` con el período vigente que se solapa."""
    respuesta = context.last_response
    assert respuesta is not None, "No hay respuesta HTTP para inspeccionar."
    cuerpo = respuesta.json()
    conflicto = cuerpo.get("conflicto") or {}
    assert conflicto.get("id") == context.vacation_period_id, (
        "El rechazo por solapamiento no identifica el período en conflicto: "
        f"{cuerpo!r}"
    )
    assert conflicto.get("estado") in ("PROGRAMADA", "EN_CURSO"), (
        f"El período en conflicto no está vigente: {conflicto!r}"
    )


# ── Ciclo completo: suspensión y reactivación ────────────────────────────────


def _crear_cuentas_satelite(context):
    """Crea las cuentas satélite del tick (sin contraseña) y espera su alta.

    Devuelve la lista de ``{"id", "email"}``. La notificación SEGURIDAD de
    ``usuario.creado`` es la evidencia observable de que auth-service ya
    persistió la cuenta, así que el tick encontrará trabajo real al procesar
    sus transiciones (eso es lo que amplía la ventana del protagonista).
    """
    cantidad = config.p5_senuelos()
    if cantidad <= 0:
        return []

    _usar_token_admin(context)
    run_id = context.run_id
    satelites = []
    for indice in range(cantidad):
        empleado_id = f"E2E-P5-SENUELO-{run_id}-{indice}"
        email = f"e2e-p5-senuelo-{run_id}-{indice}@empresa.com"
        alta = context.api.post(
            "/empleados",
            json={
                "id": empleado_id,
                "nombre": f"Satelite {indice}",
                "apellido": "E2E",
                "email": email,
                "numeroEmpleado": f"EMP-{empleado_id}",
                "cargo": "QA",
                "area": "Tecnología",
                "departamentoId": config.E2E_P5_DEPARTMENT_ID,
                "fechaIngreso": "2026-01-15",
                "estado": "ACTIVO",
            },
        )
        assert alta.status_code == 201, (
            f"POST /empleados (satélite {empleado_id!r}) devolvió "
            f"{alta.status_code}; se esperaba 201. "
            f"Cuerpo (recorte): {alta.text[:300]!r}"
        )
        satelites.append({"id": empleado_id, "email": email})

    pendientes = {satelite["id"] for satelite in satelites}

    def todas_las_cuentas_existen():
        for empleado_id in list(pendientes):
            respuesta = context.api.get(f"/notificaciones/{empleado_id}")
            if respuesta.status_code == 200 and any(
                notificacion.get("tipo") == "SEGURIDAD"
                for notificacion in respuesta.json()
            ):
                pendientes.discard(empleado_id)
        return not pendientes

    try:
        esperar_hasta_que(
            todas_las_cuentas_existen,
            descripcion=(
                f"la creación de las {cantidad} cuentas satélite en auth-service"
            ),
            max_intentos=60,
            intervalo_ms=500,
            timeout_s=30.0,
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} Cuentas sin notificación SEGURIDAD: "
            f"{sorted(pendientes)!r}. ¿Está auth-service consumiendo "
            "empleado.creado?"
        ) from exc

    return satelites


def _programar_periodos_satelite(context, satelites):
    """Programa ``hoy -> hoy`` para cada satélite, en el mismo tick.

    Se ejecuta inmediatamente después del período del protagonista para que
    todos compartan tick (la ventana de ejecución entre POSTs es de decenas
    de milisegundos).
    """
    hoy = config.hoy_utc()
    for satelite in satelites:
        respuesta = _post_vacacion(
            context,
            empleado_id=satelite["id"],
            fecha_inicio=hoy,
            fecha_fin=hoy,
            descripcion=f"el período del satélite {satelite['id']!r}",
        )
        assert respuesta.status_code == 201, (
            f"POST /vacaciones (satélite {satelite['id']!r}) devolvió "
            f"{respuesta.status_code}; se esperaba 201. "
            f"Cuerpo (recorte): {respuesta.text[:300]!r}"
        )


@when("programo un período de vacaciones que inicia de inmediato")
def step_programar_periodo_inmediato(context):
    """Programa ``hoy -> hoy`` (estrategia demo) y prepara los satélite.

    Orden deliberado: primero existen las cuentas satélite (su creación tarda
    ~1-2 s y no debe solaparse con el tick), luego se programa el período del
    protagonista y ACTO SEGUIDO los de los satélite, para que todo el
    conjunto transicione en el mismo tick del scheduler.
    """
    _requerir_empleado_activo(context)
    _usar_token_admin(context)

    satelites = _crear_cuentas_satelite(context)

    hoy = config.hoy_utc()
    context.last_response = _post_vacacion(
        context,
        empleado_id=context.active_employee_id,
        fecha_inicio=hoy,
        fecha_fin=hoy,
        descripcion="el período del empleado protagonista (hoy -> hoy)",
    )
    assert context.last_response.status_code == 201, (
        f"POST /vacaciones (protagonista) devolvió "
        f"{context.last_response.status_code}; se esperaba 201. "
        f"Cuerpo (recorte): {context.last_response.text[:300]!r}"
    )
    context.vacation_period_id = context.last_response.json().get("id")
    context.vacation_period_dates = (hoy, hoy)

    _programar_periodos_satelite(context, satelites)
    context.p5_senuelos = satelites


def _estado_periodo(context):
    """Estado actual del período del escenario (para diagnósticos)."""
    if not context.vacation_period_id:
        return "sin período registrado"
    respuesta = context.api.get(f"/vacaciones/{context.vacation_period_id}")
    if respuesta.status_code != 200:
        return f"HTTP {respuesta.status_code}"
    return respuesta.json().get("estado", "?")


@then("eventualmente el empleado no puede iniciar sesión")
def step_eventualmente_no_puede_entrar(context):
    """Polling negativo: espera el 401 de la suspensión por vacaciones.

    Sondea el login con la contraseña correcta hasta ver 401 (la cuenta
    quedó SUSPENDIDA_TEMPORAL). Si se agota ``E2E_P5_SCHEDULER_TIMEOUT_S``
    sin verlo, el escenario falla con un diagnóstico que distingue las dos
    causas: el scheduler todavía no disparó/el tick cayó entre la creación de
    los períodos, o auth-service no consumió ``vacaciones.iniciadas``.
    """
    _requerir_empleado_activo(context)
    email = context.active_employee_email
    password = context.active_employee_password
    ultimo = {"codigo": None}

    def condicion():
        respuesta = _login_directo(context, email, password)
        ultimo["codigo"] = respuesta.status_code
        return respuesta.status_code == 401

    timeout = config.p5_scheduler_timeout_s()
    try:
        esperar_hasta_que(
            condicion,
            descripcion=(
                "el rechazo de login por vacaciones (HTTP 401, cuenta "
                "SUSPENDIDA_TEMPORAL)"
            ),
            max_intentos=100000,
            intervalo_ms=config.p5_login_interval_ms(),
            timeout_s=timeout,
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} El login siguió devolviendo {ultimo['codigo']} (cuenta "
            f"ACTIVA) durante {timeout:.0f}s. Estado del período "
            f"{context.vacation_period_id!r}: {_estado_periodo(context)}. "
            "Causas posibles: el scheduler aún no ejecutó el tick, el tick "
            "cayó justo entre la creación del período del protagonista y la "
            "de los satélite (ventana sin amplificar), o auth-service no "
            "consumió vacaciones.iniciadas. Reejecutá el escenario; si "
            "persiste, revisá los consumidores de RabbitMQ."
        ) from exc


@then("eventualmente el empleado puede iniciar sesión nuevamente")
def step_eventualmente_puede_entrar(context):
    """Polling: espera el 200 de la reactivación al finalizar las vacaciones.

    La reactivación la dispara ``vacaciones.finalizadas`` en el mismo tick, a
    milisegundos del 401, así que el presupuesto es corto. Si se agota, la
    cuenta quedó suspendida sin reactivar: se falla con diagnóstico en vez de
    asumir el caso feliz.
    """
    _requerir_empleado_activo(context)
    email = context.active_employee_email
    password = context.active_employee_password
    ultimo = {"codigo": None}

    def condicion():
        respuesta = _login_directo(context, email, password)
        ultimo["codigo"] = respuesta.status_code
        return respuesta.status_code == 200

    timeout = config.p5_reactivacion_timeout_s()
    try:
        esperar_hasta_que(
            condicion,
            descripcion=(
                "el login 200 tras finalizar las vacaciones (cuenta ACTIVA "
                "de nuevo)"
            ),
            max_intentos=100000,
            intervalo_ms=config.p5_login_interval_ms(),
            timeout_s=timeout,
        )
    except TimeoutException as exc:
        raise TimeoutException(
            f"{exc} El login siguió devolviendo {ultimo['codigo']} durante "
            f"{timeout:.0f}s después de haber observado la suspensión. Estado "
            f"del período {context.vacation_period_id!r}: "
            f"{_estado_periodo(context)}. ¿auth-service consumió "
            "vacaciones.finalizadas?"
        ) from exc


@then("el período de vacaciones quedó finalizado")
def step_periodo_finalizado(context):
    """El período quedó FINALIZADA (el scheduler completó el ciclo)."""
    _requerir_empleado_activo(context)
    _usar_token_admin(context)
    estado = _estado_periodo(context)
    assert estado == "FINALIZADA", (
        f"El período {context.vacation_period_id!r} quedó en estado {estado!r}; "
        "se esperaba FINALIZADA tras reactivarse la cuenta."
    )


@then("eventualmente se notificó la suspensión temporal por vacaciones")
def step_notificacion_suspension(context):
    """Notificación CUENTA de la suspensión temporal (motivo VACACIONES)."""

    def es_la_suspension(notificacion):
        mensaje = notificacion.get("mensaje", "")
        return (
            notificacion.get("tipo") == "CUENTA"
            and notificacion.get("destinatario") == context.active_employee_email
            and "desactivada temporalmente" in mensaje
            and "VACACIONES" in mensaje
        )

    _esperar_notificacion(
        context,
        es_la_suspension,
        descripcion=(
            "la notificación CUENTA de suspensión temporal por vacaciones"
        ),
    )


@then("eventualmente se notificó la reactivación al finalizar las vacaciones")
def step_notificacion_reactivacion(context):
    """Notificación CUENTA de la reactivación (motivo FIN_VACACIONES)."""

    def es_la_reactivacion(notificacion):
        mensaje = notificacion.get("mensaje", "")
        return (
            notificacion.get("tipo") == "CUENTA"
            and notificacion.get("destinatario") == context.active_employee_email
            and "reactivada" in mensaje
            and "FIN_VACACIONES" in mensaje
        )

    _esperar_notificacion(
        context,
        es_la_reactivacion,
        descripcion=(
            "la notificación CUENTA de reactivación al finalizar las vacaciones"
        ),
    )
