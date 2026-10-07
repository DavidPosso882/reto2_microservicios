"""Autenticación para los Antecedentes (Background) de los features E2E.

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

Credenciales (nunca en los ``.feature``)
----------------------------------------
* ``ADMIN_EMAIL`` / ``ADMIN_PASSWORD`` para el rol ``"admin"``.
* ``USER_EMAIL`` / ``USER_PASSWORD`` para el rol ``"user"``.

Si faltan, el escenario falla con un mensaje que indica la variable esperada.
"""

from __future__ import annotations

from behave import given

from support import config


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

    payload = response.json()
    # El contrato de Reto 5 devuelve `accessToken`; se acepta `token` como alias.
    token = payload.get("accessToken") or payload.get("token")
    assert token, (
        "POST /auth/login respondió 200 pero sin token utilizable "
        f"(claves: {sorted(payload)!r})."
    )

    context.token = token
    context.tokens[role.strip().lower()] = token
    context.api.set_token(token)
