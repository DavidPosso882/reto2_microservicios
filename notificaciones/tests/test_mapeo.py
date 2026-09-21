"""Mapping tests: one per catalog event (sections 3.1, 3.3, 3.8)."""

from app.mensajes import construir_notificacion

from tests.conftest import (
    DATA_CREADO,
    DATA_RETIRADO,
    DATA_VACACIONES,
    evento_envelope,
)


def test_empleado_creado_genera_bienvenida():
    n = construir_notificacion(evento_envelope("empleado.creado", DATA_CREADO))
    assert n.tipo == "BIENVENIDA"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "Juan" in n.mensaje and "Pérez" in n.mensaje
    assert "bienvenido" in n.mensaje.lower()


def test_empleado_retirado_genera_desvinculacion():
    n = construir_notificacion(evento_envelope("empleado.retirado", DATA_RETIRADO))
    assert n.tipo == "DESVINCULACION"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "finalizado" in n.mensaje.lower()


def test_vacaciones_programadas_genera_vacaciones():
    n = construir_notificacion(evento_envelope("vacaciones.programadas", DATA_VACACIONES))
    assert n.tipo == "VACACIONES"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "2026-12-15" in n.mensaje and "2026-12-30" in n.mensaje


def test_tipo_desconocido_rechazado():
    import pytest

    from app.mensajes import TipoEventoDesconocido

    with pytest.raises(TipoEventoDesconocido):
        construir_notificacion(evento_envelope("empleado.actualizado", DATA_CREADO))
