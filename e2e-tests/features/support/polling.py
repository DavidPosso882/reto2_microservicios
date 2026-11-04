"""Espera activa (polling) de eventos asíncronos (Reto 6, Punto 4).

Los flujos de onboarding son asíncronos: el alta de un empleado viaja por
RabbitMQ hasta auth-service (que crea la cuenta) y hasta
notificaciones-service (que simula el envío del email). Los escenarios no
pueden asumir que el evento ya fue procesado cuando el ``POST /empleados``
responde 201, pero tampoco deben dormir un tiempo fijo: eso haría la suite
lenta y frágil.

``esperar_hasta_que`` implementa el patrón correcto: evalúa la condición de
inmediato (éxito temprano si el evento ya fue procesado), y si todavía no se
cumple reintenta cada ``intervalo_ms`` hasta agotar ``max_intentos`` o
``timeout_s``. Al agotarse lanza ``TimeoutException`` con diagnóstico.

Parámetros por defecto (justificados en el README del proyecto)
---------------------------------------------------------------
* ``max_intentos=15`` + ``intervalo_ms=2000``: peor caso ~28 s, dentro del
  presupuesto de ~30 s y suficiente para tolerar la latencia de RabbitMQ más
  los consumidores. Un intervalo más corto solo agrega carga con retorno nulo:
  el evento asíncrono típico se materializa en <1 s, pero hasta que el
  consumer lo procesa no hay nada nuevo que un sondeo más frecuente pueda ver.
* ``timeout_s=30.0``: techo global explícito; ningún escenario espera más que
  el presupuesto del P3.
* La primera evaluación es inmediata, así que en el caso feliz habitual el
  escenario continúa sin penalización aunque el intervalo sea de 2 s.

Los steps nunca usan ``time.sleep`` fijo: la única espera del proyecto es el
intervalo entre reintentos de este helper.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import requests

DEFAULT_MAX_INTENTOS = 15
DEFAULT_INTERVALO_MS = 2000
DEFAULT_TIMEOUT_S = 30.0


class TimeoutException(AssertionError):
    """La condición no se cumplió dentro del presupuesto de espera.

    Hereda de ``AssertionError`` para que Behave lo reporte como un fallo
    claro del escenario, con el diagnóstico incorporado, en vez de un error
    genérico de infraestructura.
    """


def esperar_hasta_que(
    condicion: Callable[[], Any],
    *,
    descripcion: str = "la condición",
    max_intentos: int = DEFAULT_MAX_INTENTOS,
    intervalo_ms: int = DEFAULT_INTERVALO_MS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Any:
    """Reintenta ``condicion`` hasta que devuelva un valor veraz.

    :param condicion: callable sin argumentos que hace el sondeo y devuelve un
        valor veraz cuando el evento ya se materializó (ese valor se retorna),
        o un valor falsy mientras no haya novedad. Las ``RequestException`` de
        ``requests`` se cuentan como intento fallido y se reintentan.
    :param descripcion: texto del evento esperado, usado en el diagnóstico.
    :param max_intentos: cantidad máxima de evaluaciones (>= 1).
    :param intervalo_ms: espera entre intentos, en milisegundos.
    :param timeout_s: presupuesto total de la espera, en segundos.
    :returns: el primer resultado veraz de ``condicion``.
    :raises TimeoutException: si se agotan los intentos o el timeout, con el
        detalle de intentos, tiempo transcurrido y último resultado/error.
    """
    if max_intentos < 1:
        raise ValueError("max_intentos debe ser >= 1")
    if intervalo_ms < 0:
        raise ValueError("intervalo_ms no puede ser negativo")
    if timeout_s <= 0:
        raise ValueError("timeout_s debe ser > 0")

    intervalo_s = intervalo_ms / 1000.0
    inicio = time.monotonic()
    ultimo_resultado: Any = None
    ultimo_error: BaseException | None = None
    intentos = 0

    while intentos < max_intentos:
        intentos += 1
        try:
            resultado = condicion()
        except requests.RequestException as exc:
            ultimo_error = exc
        else:
            if resultado:
                return resultado
            ultimo_resultado = resultado

        restante = timeout_s - (time.monotonic() - inicio)
        if intentos >= max_intentos or restante <= 0:
            break
        time.sleep(min(intervalo_s, restante))

    transcurrido = time.monotonic() - inicio
    if ultimo_error is not None:
        detalle = f"último error HTTP: {type(ultimo_error).__name__}: {ultimo_error}"
    else:
        detalle = f"último resultado: {ultimo_resultado!r}"[:300]

    raise TimeoutException(
        f"No se cumplió {descripcion} tras {intentos} intentos "
        f"({transcurrido:.1f}s, intervalo {intervalo_ms}ms, timeout "
        f"{timeout_s:.0f}s). {detalle}."
    )


# Alias con el nombre camelCase usado en el enunciado del Reto 6
# (`esperarHastaQue`). El proyecto usa snake_case; ambos nombres apuntan al
# mismo comportamiento.
esperarHastaQue = esperar_hasta_que
