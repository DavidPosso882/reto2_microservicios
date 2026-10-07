"""Espera activa (polling) — stub documentado, se implementa en P4.

En P2 solo existe el humo del gateway, que es síncrono: no hay nada que
esperar. En P4 (eventos asíncronos: notificaciones y ciclo de vida de
vacaciones) este módulo expondrá un helper de reintentos, del estilo:

    wait_until(
        lambda: context.api.get("/notificaciones").json(),
        predicate=lambda body: any(n["estado"] == "ENVIADA" for n in body),
        timeout_s=15,
        interval_s=0.5,
    )

Hasta entonces, cualquier uso falla explícitamente para no dar una falsa
sensación de soporte.
"""

from __future__ import annotations

from typing import Any


def wait_until(*_args: Any, **_kwargs: Any) -> Any:
    """Placeholder: no usar todavía (queda para P4)."""
    raise NotImplementedError(
        "El polling se implementa en P4; en P2 el humo no lo necesita."
    )
