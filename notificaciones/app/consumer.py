"""RabbitMQ consumer for the ecosystem event catalog (CATALOGO_EVENTOS.md).

Declares the durable topic exchange `ecosistema.eventos`, the durable queue
`q.notificaciones`, binds the three routing keys this service consumes, and
ACKs manually only after the effect (notification + dedup ledger row) is
persisted. Startup tolerates a broker that is not ready yet by retrying with
exponential backoff instead of dying.
"""

import json
import logging
import threading
import time

import pika
from pika.exceptions import AMQPConnectionError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal
from app.models import EventoProcesado
from app.mensajes import TipoEventoDesconocido, construir_notificacion, log_envio

logger = logging.getLogger("notificaciones.consumer")

EXCHANGE = "ecosistema.eventos"
QUEUE = "q.notificaciones"
ROUTING_KEYS = (
    "empleado.creado",
    "empleado.retirado",
    "vacaciones.programadas",
)

# Broker availability retry (exponential backoff, capped)
REINTENTOS_MAX = 12
BACKOFF_INICIAL_S = 2.0
BACKOFF_MAX_S = 30.0

# Transient (DB) failures: exponential backoff before requeueing, so a
# prolonged outage cannot hot-loop the redelivery of the same message.
REQUEUE_BACKOFF_INICIAL_S = 0.5
REQUEUE_BACKOFF_MAX_S = 10.0


class MensajeEnvenenado(Exception):
    """Permanent envelope error: the message can never be processed (poison).

    Raised for payloads this service must discard with ACK instead of
    requeueing: an envelope without `id`, JSON that is not an object, an
    unknown event type, or `data` missing the fields the mapping requires.
    Requeueing these would loop forever and block the queue.
    """


def procesar_evento(session, envelope: dict) -> bool:
    """Persist dedup ledger + notification in one transaction.

    Returns True if the event was newly applied; False when the envelope `id`
    was already processed (duplicate).

    Raises MensajeEnvenenado when the payload is permanently invalid.
    """
    if not isinstance(envelope, dict):
        raise MensajeEnvenenado(
            f"Envelope no es un objeto JSON (es {type(envelope).__name__})."
        )

    evento_id = envelope.get("id")
    if not evento_id:
        raise MensajeEnvenenado("Envelope sin `id`; el efecto no puede deduplicarse.")

    # Dedup check inside the write transaction (belt and braces with the PK).
    ya_visto = session.execute(
        select(EventoProcesado).where(EventoProcesado.id == evento_id)
    ).scalar_one_or_none()
    if ya_visto is not None:
        logger.info("Evento duplicado (id=%s); se ignora sin repetir efecto.", evento_id)
        return False

    try:
        notificacion = construir_notificacion(envelope)
    except (TipoEventoDesconocido, KeyError, TypeError, AttributeError) as exc:
        # Permanent mapping error: retrying can never succeed (poison).
        raise MensajeEnvenenado(
            f"Envelope {evento_id} (type={envelope.get('type')!r}) no mapea "
            f"a notificacion: {exc!r}"
        ) from exc
    log_envio(notificacion)  # simulated send, before persistence
    session.add(notificacion)
    session.add(EventoProcesado(id=evento_id))
    try:
        session.commit()
        logger.info(
            "Evento %s (type=%s) procesado y persistido.",
            evento_id,
            envelope.get("type"),
        )
        return True
    except IntegrityError:
        # Concurrent duplicate between check and commit: roll back, no effect.
        session.rollback()
        logger.info("Evento duplicado detectado al insertar (id=%s).", evento_id)
        return False


class Consumer:
    """Runs in a daemon thread; survives a broker that starts later."""

    def __init__(self, host: str, port: int, user: str, password: str):
        self._host = host
        self._port = port
        self._credentials = pika.PlainCredentials(user, password)
        self._connection = None
        self._channel = None
        self._stop = threading.Event()
        self._backoff_transitorio_s = REQUEUE_BACKOFF_INICIAL_S

    # -- broker plumbing -------------------------------------------------

    def _conectar(self):
        params = pika.ConnectionParameters(
            host=self._host,
            port=self._port,
            credentials=self._credentials,
            heartbeat=30,
            blocked_connection_timeout=30,
        )
        return pika.BlockingConnection(params)

    def _configurar_topologia(self, channel):
        # Order matters: the durable topic exchange is declared FIRST, so the
        # queue/bind calls below never race against a missing exchange.
        channel.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
        channel.queue_declare(queue=QUEUE, durable=True)
        for routing_key in ROUTING_KEYS:
            channel.queue_bind(
                queue=QUEUE, exchange=EXCHANGE, routing_key=routing_key
            )

    def _esperar_broker(self):
        """Retry loop with exponential backoff until the broker accepts AMQP."""
        backoff = BACKOFF_INICIAL_S
        intento = 1
        while not self._stop.is_set() and intento <= REINTENTOS_MAX:
            try:
                self._connection = self._conectar()
                logger.info("Conectado a RabbitMQ en %s:%s.", self._host, self._port)
                return
            except AMQPConnectionError:
                logger.warning(
                    "RabbitMQ no disponible (intento %s/%s); reintentando en %.0fs...",
                    intento,
                    REINTENTOS_MAX,
                    backoff,
                )
                self._stop.wait(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX_S)
                intento += 1
        if not self._stop.is_set():
            logger.error(
                "No se pudo conectar a RabbitMQ tras %s intentos; el consumer "
                "queda inactivo pero el servicio REST sigue operativo.",
                REINTENTOS_MAX,
            )

    # -- message handling -------------------------------------------------

    def _on_message(self, channel, method, properties, body):
        routing_key = getattr(method, "routing_key", "?")
        try:
            envelope = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Poison: malformed JSON can never become a valid envelope.
            logger.error(
                "Mensaje con JSON invalido (routing_key=%s); se descarta con ACK "
                "para no bloquear la cola.",
                routing_key,
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        session = SessionLocal()
        try:
            procesar_evento(session, envelope)
        except MensajeEnvenenado as exc:
            # Poison: permanent payload error. Requeueing would loop forever
            # and block the queue; discard with ACK instead.
            session.rollback()
            logger.error(
                "Mensaje envenenado descartado con ACK (id=%s, routing_key=%s): %s",
                envelope.get("id", "?") if isinstance(envelope, dict) else "?",
                routing_key,
                exc,
            )
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return
        except Exception:
            session.rollback()
            # Transient (e.g. DB down): requeue so the event is not lost,
            # pausing with exponential backoff so an outage cannot hot-loop.
            if not self._stop.is_set():
                self._stop.wait(self._backoff_transitorio_s)
                self._backoff_transitorio_s = min(
                    self._backoff_transitorio_s * 2, REQUEUE_BACKOFF_MAX_S
                )
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            logger.exception(
                "Error transitorio persistiendo evento (routing_key=%s); "
                "se reencola con backoff.",
                routing_key,
            )
            return
        finally:
            session.close()
        self._backoff_transitorio_s = REQUEUE_BACKOFF_INICIAL_S
        # Manual ACK only AFTER the effect is persisted (or duplicate skipped).
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def _cerrar(self):
        """Close channel/connection best-effort before a reconnect pass."""
        try:
            if self._channel is not None:
                self._channel.close()
        except Exception:
            pass
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass
        self._channel = None
        self._connection = None

    def run(self):
        # Every pass: (re)connect with backoff, re-declare the topology, and
        # consume. A lost connection or a failed topology declaration retries
        # instead of killing the consumer thread.
        while not self._stop.is_set():
            self._esperar_broker()
            if self._connection is None or self._connection.is_closed:
                return
            try:
                self._channel = self._connection.channel()
                self._configurar_topologia(self._channel)
                self._channel.basic_qos(prefetch_count=1)
                self._channel.basic_consume(
                    queue=QUEUE, on_message_callback=self._on_message
                )
                logger.info(
                    "Consumer escuchando cola %s (keys: %s).",
                    QUEUE,
                    ", ".join(ROUTING_KEYS),
                )
                self._channel.start_consuming()
            except AMQPConnectionError:
                if self._stop.is_set():
                    break
                logger.warning(
                    "Conexion con RabbitMQ perdida; reintentando con backoff..."
                )
                self._cerrar()
                self._stop.wait(BACKOFF_INICIAL_S)
            except Exception:
                self._cerrar()
                if not self._stop.is_set():
                    logger.exception(
                        "Consumer termino inesperadamente; reintentando..."
                    )
                    self._stop.wait(BACKOFF_INICIAL_S)
                else:
                    break

    def stop(self):
        self._stop.set()
        try:
            if self._channel and self._channel.is_open:
                self._channel.stop_consuming()
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            pass


_consumer: Consumer | None = None
_consumer_thread: threading.Thread | None = None


def iniciar_consumer() -> None:
    global _consumer, _consumer_thread
    if _consumer is not None:
        return
    _consumer = Consumer(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        user=settings.rabbitmq_user,
        password=settings.rabbitmq_password,
    )
    _consumer_thread = threading.Thread(target=_consumer.run, name="amqp-consumer", daemon=True)
    _consumer_thread.start()


def detener_consumer() -> None:
    global _consumer, _consumer_thread
    if _consumer is not None:
        _consumer.stop()
    if _consumer_thread is not None:
        _consumer_thread.join(timeout=2)
    _consumer = None
    _consumer_thread = None
