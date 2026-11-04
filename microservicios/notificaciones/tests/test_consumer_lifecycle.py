"""Consumer lifecycle wiring and AMQP topology declaration (Reto 4, D2/D4).

No real RabbitMQ: the Consumer's broker calls are mocked and the app's
startup/shutdown hooks are observed through monkeypatched module functions.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pika
import pytest
from fastapi.testclient import TestClient

import app.consumer as consumer_module
from app.consumer import Consumer
from app.main import crear_app


def _flag(monkeypatch, enabled: bool) -> None:
    """Override the settings object seen by app.main (env-based config)."""
    monkeypatch.setattr(
        "app.main.settings", SimpleNamespace(consumer_enabled=enabled)
    )


def test_startup_arranca_consumer_y_shutdown_lo_detiene(monkeypatch):
    """CONSUMER_ENABLED=true: startup starts the consumer, shutdown stops it."""
    _flag(monkeypatch, True)
    iniciar = Mock()
    detener = Mock()
    monkeypatch.setattr("app.main.iniciar_consumer", iniciar)
    monkeypatch.setattr("app.main.detener_consumer", detener)

    with TestClient(crear_app()) as cliente:
        iniciar.assert_called_once()
        detener.assert_not_called()
        assert cliente.get("/health").status_code == 200

    detener.assert_called_once()


def test_consumer_disabled_no_arranca_nada(monkeypatch):
    """CONSUMER_ENABLED=false (API-only run): no consumer, no shutdown call."""
    _flag(monkeypatch, False)
    iniciar = Mock()
    detener = Mock()
    monkeypatch.setattr("app.main.iniciar_consumer", iniciar)
    monkeypatch.setattr("app.main.detener_consumer", detener)

    with TestClient(crear_app()) as cliente:
        assert cliente.get("/health").status_code == 200

    iniciar.assert_not_called()
    detener.assert_not_called()


def test_topologia_exchange_primero_luego_cola_y_bindings():
    """D4: exchange declared (durable topic) before queue, queue before binds."""
    consumer = Consumer("localhost", 5672, "guest", "guest")
    channel = Mock()
    consumer._configurar_topologia(channel)

    nombres = [name for name, _, _ in channel.mock_calls]
    assert nombres[0] == "exchange_declare"
    assert nombres[1] == "queue_declare"
    assert "queue_bind" in nombres
    assert nombres.index("queue_declare") < nombres.index("queue_bind")

    kwargs_exchange = channel.exchange_declare.call_args.kwargs
    assert kwargs_exchange["exchange"] == consumer_module.EXCHANGE
    assert kwargs_exchange["exchange_type"] == "topic"
    assert kwargs_exchange["durable"] is True

    kwargs_queue = channel.queue_declare.call_args.kwargs
    assert kwargs_queue["queue"] == consumer_module.QUEUE
    assert kwargs_queue["durable"] is True

    claves = [c.kwargs["routing_key"] for c in channel.queue_bind.call_args_list]
    assert claves == list(consumer_module.ROUTING_KEYS)
    assert all(
        c.kwargs["exchange"] == consumer_module.EXCHANGE
        and c.kwargs["queue"] == consumer_module.QUEUE
        for c in channel.queue_bind.call_args_list
    )


def test_fallo_de_declaracion_reintenta_en_veces_de_morir(monkeypatch):
    """D4: a topology declaration failure triggers a new pass with backoff."""
    consumer = Consumer("localhost", 5672, "guest", "guest")
    connection = Mock()
    connection.is_closed = False
    connection.is_open = True
    connection.channel.return_value = Mock()
    monkeypatch.setattr(
        consumer,
        "_esperar_broker",
        lambda: setattr(consumer, "_connection", connection),
    )
    monkeypatch.setattr(consumer_module, "BACKOFF_INICIAL_S", 0.01)

    intentos = {"topologia": 0}

    def topologia_flaky(_channel):
        intentos["topologia"] += 1
        if intentos["topologia"] == 1:
            raise pika.exceptions.AMQPConnectionError("exchange no listo")
        consumer._stop.set()
        raise RuntimeError("second pass reached, test done")

    monkeypatch.setattr(consumer, "_configurar_topologia", topologia_flaky)

    consumer.run()

    # First declaration failure did not kill the thread: it retried and the
    # second pass re-declared the topology before the test stopped it.
    assert intentos["topologia"] == 2
