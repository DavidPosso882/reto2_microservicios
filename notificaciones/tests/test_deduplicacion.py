"""Dedup tests: same envelope `id` twice must produce a single notification."""

import pytest
from sqlalchemy import select

from app.consumer import MensajeEnvenenado, procesar_evento
from app.models import EventoProcesado, Notificacion

from tests.conftest import DATA_CREADO, evento_envelope


def test_mismo_id_dos_veces_una_sola_notificacion(sesion):
    env = evento_envelope("empleado.creado", DATA_CREADO, evento_id="evt-dup")

    assert procesar_evento(sesion, env) is True
    assert procesar_evento(sesion, env) is False  # duplicate: no second effect

    notificaciones = sesion.query(Notificacion).all()
    assert len(notificaciones) == 1
    ledger = sesion.execute(select(EventoProcesado)).scalars().all()
    assert [e.id for e in ledger] == ["evt-dup"]


def test_ids_distintos_generan_notificaciones_distintas(sesion):
    assert procesar_evento(
        sesion, evento_envelope("empleado.creado", DATA_CREADO, "evt-a")
    )
    assert procesar_evento(
        sesion, evento_envelope("empleado.retirado", DATA_CREADO, "evt-b")
    )
    assert sesion.query(Notificacion).count() == 2


def test_envelope_sin_id_es_poison_y_no_genera_nada(sesion):
    """D6: an envelope without `id` is permanent (poison), not transient."""
    env = evento_envelope("empleado.creado", DATA_CREADO)
    env.pop("id")
    with pytest.raises(MensajeEnvenenado):
        procesar_evento(sesion, env)
    assert sesion.query(Notificacion).count() == 0
