"""Pasos del feature de seguridad RBAC (Reto 6, Punto 3).

Verifica contra el gateway real (``http://localhost:8080``) los cortes de
autorización del borde, observados en el stack levantado antes de fijarlos:

* Sin token / token inválido o malformado -> **401** (``authenticate``): el
  gateway no puede probar identidad alguna.
* Token USER válido: lectura -> **200**; escrituras POST/DELETE -> **403**
  (``authorizeService``). Nunca 401 en este caso: la identidad ya está probada
  y lo que falla es el permiso del rol.
* Token ADMIN: GET -> **200**, POST -> **201**, DELETE (baja lógica) -> **200**.

Los datos de prueba usan ``context.run_id`` (uuid4 por escenario, ver
``environment.py``) en los identificadores ``E2E-P3-*``, de modo que cada
corrida y cada escenario son independientes y no chocan entre sí.
"""

from __future__ import annotations

from behave import given, then, when

from support import config


def _usar_token(context, role):
    """Aplica el Bearer del rol pedido o falla si el escenario no lo tiene."""
    token = context.tokens.get(role.strip().lower())
    assert token, (
        f"No hay token para el rol {role!r} en este escenario; ejecutá antes "
        f"el paso de login/activación correspondiente."
    )
    context.api.set_token(token)


def _empleado_de_prueba(context, prefijo):
    """Payload canónico de un empleado ``E2E-P3`` único por escenario."""
    sufijo = context.run_id
    return {
        "id": f"{prefijo}-{sufijo}",
        "nombre": "Prueba",
        "apellido": "RBAC",
        "email": f"{prefijo.lower()}-{sufijo}@empresa.com",
        "numeroEmpleado": f"EMP-{prefijo}-{sufijo}",
        "cargo": "QA",
        "area": "Tecnología",
        "departamentoId": config.E2E_DEPARTMENT_ID,
        "fechaIngreso": "2026-01-15",
        "estado": "ACTIVO",
    }


@given('que existe el departamento "{departamento_id}"')
def step_departamento_disponible(context, departamento_id):
    """Asegura el departamento E2E pedido (idempotente) usando ADMIN.

    Reutilizado por los Puntos 3 y 4: el feature indica el id
    (``E2E-P3-DEPT`` / ``E2E-P4-DEPT``). En un stack recién levantado la tabla
    de departamentos está vacía y sin departamento válido el POST /empleados
    daría 400. Si ya existe (corridas anteriores), el GET devuelve 200 y no se
    vuelve a crear.
    """
    token = context.tokens.get("admin")
    assert token, (
        "No hay token ADMIN; el Antecedentes debe ejecutar "
        '`Dado que inicio sesión como "admin"` antes de asegurar el departamento.'
    )
    context.api.set_token(token)

    respuesta = context.api.get(f"/departamentos/{departamento_id}")
    if respuesta.status_code == 404:
        respuesta = context.api.post(
            "/departamentos",
            json={
                "id": departamento_id,
                "nombre": f"Departamento {departamento_id}",
                "descripcion": (
                    "Departamento sintético del proyecto E2E, asegurado de "
                    "forma idempotente por el Antecedentes"
                ),
            },
        )
        assert respuesta.status_code == 201, (
            f"POST /departamentos devolvió {respuesta.status_code} al crear "
            f"{departamento_id!r}; se esperaba 201. "
            f"Cuerpo (recorte): {respuesta.text[:300]!r}"
        )
    else:
        assert respuesta.status_code == 200, (
            f"GET /departamentos/{departamento_id} devolvió "
            f"{respuesta.status_code}; se esperaba 200 (ya existe) o 404 (crear)."
        )
    context.last_response = respuesta


@when("consulto el listado de empleados sin token")
def step_listar_sin_token(context):
    """GET /empleados sin credencial: la sesión del escenario queda sin Bearer."""
    context.api.set_token(None)
    context.token = None
    context.last_response = context.api.get("/empleados")


@when("consulto el listado de empleados con un token inválido")
def step_listar_token_invalido(context):
    """Bearer con forma de JWT pero firma inválida (no verifica con el secreto)."""
    context.api.set_token("esto.no.es.un.jwt")
    context.last_response = context.api.get("/empleados")


@when("consulto el listado de empleados con un token malformado")
def step_listar_token_malformado(context):
    """Bearer que ni siquiera tiene la forma de un JWT."""
    context.api.set_token("token-sin-formato-jwt")
    context.last_response = context.api.get("/empleados")


@when('consulto el listado de empleados como "{role}"')
def step_listar_como_rol(context, role):
    """GET /empleados con el Bearer del rol (USER y ADMIN pueden leer)."""
    _usar_token(context, role)
    context.last_response = context.api.get("/empleados")


@when('registro un empleado como "{role}"')
def step_registrar_como_rol(context, role):
    """POST /empleados con el Bearer del rol; recuerda el id para el DELETE."""
    _usar_token(context, role)
    payload = _empleado_de_prueba(context, "E2E-P3")
    context.created_employee_id = payload["id"]
    context.last_response = context.api.post("/empleados", json=payload)


@when('intento registrar un empleado como "{role}"')
def step_intento_registrar_como_rol(context, role):
    """POST /empleados que debe ser rechazado para un rol de solo lectura."""
    _usar_token(context, role)
    context.last_response = context.api.post(
        "/empleados", json=_empleado_de_prueba(context, "E2E-P3-DENEGADO")
    )


@when('intento retirar el empleado del usuario como "{role}"')
def step_intento_retirar_empleado_usuario(context, role):
    """DELETE del empleado propio del token USER: la escritura debe dar 403."""
    _usar_token(context, role)
    assert context.user_employee_id, (
        "No hay empleado USER en el escenario; ejecutá antes "
        "`Dado que tengo un token de usuario activo`."
    )
    context.last_response = context.api.delete(
        f"/empleados/{context.user_employee_id}"
    )


@when('retiro el empleado registrado como "{role}"')
def step_retirar_empleado_registrado(context, role):
    """DELETE del empleado dado de alta por el escenario (baja lógica)."""
    _usar_token(context, role)
    assert context.created_employee_id, (
        "No hay empleado registrado en el escenario; ejecutá antes "
        '`Cuando registro un empleado como "ADMIN"`.'
    )
    context.last_response = context.api.delete(
        f"/empleados/{context.created_employee_id}"
    )


@then("la respuesta confirma el empleado registrado")
def step_respuesta_confirma_empleado(context):
    """El POST 201 devuelve como id exactamente el empleado que se pidió."""
    respuesta = context.last_response
    assert respuesta is not None and respuesta.status_code == 201, (
        "La última respuesta no es el 201 del alta registrada "
        f"(código/estado: {getattr(respuesta, 'status_code', None)})."
    )
    cuerpo = respuesta.json()
    assert cuerpo.get("id") == context.created_employee_id, (
        f"El POST devolvió el id {cuerpo.get('id')!r}; se esperaba "
        f"{context.created_employee_id!r}."
    )
