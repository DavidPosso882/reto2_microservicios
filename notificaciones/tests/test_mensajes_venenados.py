"""Poison-message handling: permanent payload errors discard with ACK (D6).

No real RabbitMQ: `Consumer._on_message` is driven directly with a mocked
channel and the persisted effects are asserted on the SQLite test database.

Permanent (poison) errors -> ACK discard, zero requeue, zero notifications:
  - body that is not valid JSON (already ACKed before this fix; kept as guard)
  - valid JSON that is not a JSON object
  - envelope without `id`
  - unknown event type
  - `data` missing the fields the mapping requires (the D6 evidence: an
    `empleado.creado` published with `empleadoId` instead of `id`)

Transient (DB) errors -> NACK + requeue with backoff; never an ACK.
A duplicate valid event keeps being discarded by dedup with ACK: dedup is
not a poison case.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError

import app.consumer as consumer_module
from app.consumer import Consumer, MensajeEnvenenado, procesar_evento
from app.models import EventoProcesado, Notificacion

from tests.conftest import (
    DATA_CREADO,
    DATA_RETIRADO,
    DATA_VACACIONES,
    evento_envelope,
)


def _sin(data: dict, clave: str) -> dict:
    """Copy of `data` without `clave` (simulates an incomplete payload)."""
    return {k: v for k, v in data.items() if k != clave}


def _metodo_amqp(delivery_tag: int = 1, routing_key: str = "empleado.creado"):
    return SimpleNamespace(delivery_tag=delivery_tag, routing_key=routing_key)


def _consumer() -> Consumer:
    return Consumer("localhost", 5672, "guest", "guest")


def _cuerpo(envelope: dict) -> bytes:
    return json.dumps(envelope).encode("utf-8")


# -- classification at the pipeline level (procesar_evento) -----------------


def test_envelope_que_no_es_objeto_es_poison(sesion):
    with pytest.raises(MensajeEnvenenado):
        procesar_evento(sesion, ["no", "es", "un", "objeto"])
    assert sesion.query(Notificacion).count() == 0


def test_tipo_desconocido_es_poison(sesion):
    env = evento_envelope("empleado.actualizado", DATA_CREADO, "evt-poison-1")
    with pytest.raises(MensajeEnvenenado):
        procesar_evento(sesion, env)
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


@pytest.mark.parametrize(
    "tipo, data",
    [
        # The D6 evidence: empleado.creado with `empleadoId` instead of `id`.
        ("empleado.creado", {**_sin(DATA_CREADO, "id"), "empleadoId": "E001"}),
        ("empleado.creado", _sin(DATA_CREADO, "email")),
        ("empleado.retirado", _sin(DATA_RETIRADO, "email")),
        ("vacaciones.programadas", _sin(DATA_VACACIONES, "empleadoEmail")),
        ("vacaciones.programadas", _sin(DATA_VACACIONES, "fechaFin")),
    ],
)
def test_data_incompleta_es_poison(sesion, tipo, data):
    env = evento_envelope(tipo, data, "evt-poison-2")
    with pytest.raises(MensajeEnvenenado):
        procesar_evento(sesion, env)
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


# -- classification at the AMQP level (Consumer._on_message) -----------------


def test_json_malformado_se_descarta_con_ack(sesion):
    canal = Mock()
    _consumer()._on_message(canal, _metodo_amqp(), None, b"{esto no es json")

    canal.basic_ack.assert_called_once_with(delivery_tag=1)
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


def test_json_valido_que_no_es_objeto_se_descarta_con_ack(sesion):
    canal = Mock()
    _consumer()._on_message(canal, _metodo_amqp(), None, b'["lista", "suelta"]')

    canal.basic_ack.assert_called_once_with(delivery_tag=1)
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 0


def test_envelope_sin_id_se_descarta_con_ack(sesion):
    env = evento_envelope("empleado.creado", DATA_CREADO)
    env.pop("id")

    canal = Mock()
    _consumer()._on_message(canal, _metodo_amqp(), None, _cuerpo(env))

    canal.basic_ack.assert_called_once_with(delivery_tag=1)
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


def test_tipo_desconocido_se_descarta_con_ack_sin_reencolar(sesion):
    """D6: future producers must never block the queue with unknown types."""
    env = evento_envelope("empleado.actualizado", DATA_CREADO, "evt-unknown")
    canal = Mock()

    _consumer()._on_message(
        canal, _metodo_amqp(routing_key="empleado.actualizado"), None, _cuerpo(env)
    )

    canal.basic_ack.assert_called_once_with(delivery_tag=1)
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


def test_data_con_empleadoid_en_vez_de_id_se_descarta_con_ack(sesion):
    """D6 regression: the exact evidence payload ACK-discards, never requeues."""
    data = {**_sin(DATA_CREADO, "id"), "empleadoId": "E001"}
    env = evento_envelope("empleado.creado", data, "evt-d6")
    canal = Mock()

    _consumer()._on_message(canal, _metodo_amqp(), None, _cuerpo(env))

    canal.basic_ack.assert_called_once_with(delivery_tag=1)
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


# -- transient errors still requeue ------------------------------------------


class _SesionConFalloBD:
    """Session stub whose first DB access raises a transient error."""

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexion perdida"))

    def rollback(self):
        pass

    def close(self):
        pass


def test_error_transitorio_se_reencola_con_nack(sesion, monkeypatch):
    """A DB outage must NACK+requeue (never lose the event) with backoff."""
    consumer = _consumer()
    canal = Mock()
    pausas = []
    monkeypatch.setattr(consumer._stop, "wait", lambda s: pausas.append(s))
    monkeypatch.setattr(
        consumer_module, "SessionLocal", lambda: _SesionConFalloBD()
    )

    consumer._on_message(
        canal,
        _metodo_amqp(),
        None,
        _cuerpo(evento_envelope("empleado.creado", DATA_CREADO, "evt-transient")),
    )

    canal.basic_nack.assert_called_once_with(delivery_tag=1, requeue=True)
    canal.basic_ack.assert_not_called()
    assert pausas == [consumer_module.REQUEUE_BACKOFF_INICIAL_S]
    assert consumer._backoff_transitorio_s == (
        consumer_module.REQUEUE_BACKOFF_INICIAL_S * 2
    )
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


def test_backoff_transitorio_se_reinicia_tras_procesar_bien(sesion, monkeypatch):
    """Once the DB recovers, the requeue backoff returns to its initial value."""
    consumer = _consumer()
    canal = Mock()
    pausas = []
    monkeypatch.setattr(consumer._stop, "wait", lambda s: pausas.append(s))

    original = consumer_module.procesar_evento
    intentos = {"n": 0}

    def procesar_inestable(session, envelope):
        intentos["n"] += 1
        if intentos["n"] in (1, 3):
            raise OperationalError("SELECT 1", {}, Exception("db caida"))
        return original(session, envelope)

    monkeypatch.setattr(consumer_module, "procesar_evento", procesar_inestable)

    env = _cuerpo(evento_envelope("empleado.creado", DATA_CREADO, "evt-recover"))
    consumer._on_message(canal, _metodo_amqp(delivery_tag=1), None, env)
    consumer._on_message(canal, _metodo_amqp(delivery_tag=2), None, env)
    consumer._on_message(canal, _metodo_amqp(delivery_tag=3), None, env)

    assert canal.basic_ack.call_count == 1  # only the successful middle pass
    assert pausas == [
        consumer_module.REQUEUE_BACKOFF_INICIAL_S,
        consumer_module.REQUEUE_BACKOFF_INICIAL_S,
    ]
    assert canal.basic_nack.call_count == 2


# -- dedup criterion intact ---------------------------------------------------


def test_evento_duplicado_valido_sigue_descartandose_por_dedup_con_ack(sesion):
    """A duplicated valid event ACKs twice with a single effect: not poison."""
    env = _cuerpo(evento_envelope("empleado.creado", DATA_CREADO, "evt-dedup-d6"))
    consumer = _consumer()
    canal = Mock()

    consumer._on_message(canal, _metodo_amqp(delivery_tag=1), None, env)
    consumer._on_message(canal, _metodo_amqp(delivery_tag=2), None, env)

    assert canal.basic_ack.call_count == 2
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 1
    assert sesion.query(EventoProcesado).count() == 1
