"""Métrica de negocio notificaciones_enviadas_total{tipo} (T8)."""
import pytest

from app.consumer import procesar_evento
from app.observability import NOTIFICACIONES_ENVIADAS

pytestmark = pytest.mark.skipif(
    NOTIFICACIONES_ENVIADAS is None, reason="sin prometheus_client"
)


def _valor(tipo="BIENVENIDA"):
    for muestra in NOTIFICACIONES_ENVIADAS.collect()[0].samples:
        if muestra.name.endswith("_total") and muestra.labels.get("tipo") == tipo:
            return muestra.value
    return 0.0


def test_procesar_evento_incrementa_contador(sesion):
    antes = _valor()
    ok = procesar_evento(sesion, {
        "id": "evt-metrica-1", "type": "empleado.creado", "version": "1.0",
        "occurredAt": "2026-11-04T00:00:00Z", "producer": "empleados-service",
        "data": {"id": "E1", "nombre": "Ada", "apellido": "L",
                 "email": "ada@empresa.com"},
    })
    assert ok is True
    assert _valor() == antes + 1.0


def test_duplicado_no_incrementa(sesion):
    env = {
        "id": "evt-metrica-2", "type": "empleado.creado", "version": "1.0",
        "occurredAt": "2026-11-04T00:00:00Z", "producer": "empleados-service",
        "data": {"id": "E2", "nombre": "Ada", "apellido": "L",
                 "email": "ada2@empresa.com"},
    }
    assert procesar_evento(sesion, env) is True
    antes = _valor()
    assert procesar_evento(sesion, env) is False
    assert _valor() == antes
