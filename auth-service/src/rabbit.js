import amqp from 'amqplib';
import { randomUUID } from 'node:crypto';
import { context, trace } from '@opentelemetry/api';
import { logger } from './observability/logger.js';
import { recordEventoPublicado } from './observability/metrics.js';
import { extractContext, injectContext, tracer } from './observability/tracing.js';

/**
 * RabbitMQ integration for auth-service (CATALOGO_EVENTOS.md §2).
 *
 * Consumes account-lifecycle inputs on its own durable queue:
 *   q.auth ← empleado.creado, empleado.retirado, vacaciones.iniciadas, vacaciones.finalizadas
 * Publishes account-lifecycle outcomes on the topic exchange:
 *   usuario.creado, usuario.recuperacion, cuenta.activada, cuenta.desactivada
 *
 * Manual ACK after the effect AND the envelope id are persisted
 * (usuarios + eventos_procesados), so a crash before ACK replays the message
 * and the dedup ledger makes the retry idempotent.
 */

const EXCHANGE = 'ecosistema.eventos';
const QUEUE = 'q.auth';
export const ROUTING_KEYS = [
  'empleado.creado',
  'empleado.retirado',
  'vacaciones.iniciadas',
  'vacaciones.finalizadas',
];

// Broker availability retry (exponential backoff, capped), aligned with the
// notificaciones-service approach so all consumers boot sanely together.
const REINTENTOS_MAX = 12;
const BACKOFF_INICIAL_S = 2.0;
const BACKOFF_MAX_S = 30.0;

// Transient failures: growing backoff before requeueing so a prolonged
// outage cannot hot-loop redelivery of the same message.
const REQUEUE_BACKOFF_INICIAL_MS = 500;
const REQUEUE_BACKOFF_MAX_MS = 10000;

function buildRabbitUrl() {
  const host = process.env.RABBITMQ_HOST || 'localhost';
  const port = process.env.RABBITMQ_PORT || '5672';
  const user = process.env.RABBITMQ_USER || 'admin';
  const password = process.env.RABBITMQ_PASSWORD || 'admin';
  return `amqp://${encodeURIComponent(user)}:${encodeURIComponent(password)}@${host}:${port}`;
}

// Indirection point so integration tests can stub the low-level amqplib
// connection without patching module singletons.
export function _setAmqpConnectForTests(fn) {
  _connect = fn;
}
let _connect = () => amqp.connect(buildRabbitUrl());

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function conectarConBackoff() {
  let espera = BACKOFF_INICIAL_S;
  for (let intento = 1; intento <= REINTENTOS_MAX; intento++) {
    try {
      return await _connect();
    } catch (err) {
      logger.warn('rabbit_connect_retry', {
        attempt: intento,
        maxAttempts: REINTENTOS_MAX,
        error: err.message,
      });
      if (intento === REINTENTOS_MAX) {
        throw err;
      }
      await sleep(espera * 1000);
      espera = Math.min(espera * 2, BACKOFF_MAX_S);
    }
  }
  throw new Error('No fue posible conectar al message broker');
}

/**
 * Applies one event envelope to the account domain. Returns nothing; throws
 * only on transient (retryable) failures — permanent payload errors are
 * handled by the caller as poison messages.
 */
export async function aplicarEvento(service, envelope) {
  const data = envelope.data || {};
  switch (envelope.type) {
    case 'empleado.creado':
      await service.aplicarEmpleadoCreado(data);
      break;
    case 'empleado.retirado':
      await service.aplicarEmpleadoRetirado(data);
      break;
    case 'vacaciones.iniciadas':
      await service.aplicarVacacionesIniciadas(data);
      break;
    case 'vacaciones.finalizadas':
      await service.aplicarVacacionesFinalizadas(data);
      break;
    default:
      // Unknown routing key: cannot belong to this consumer's contract, ACK
      // and drop (the queue only receives bound keys, but stay defensive).
      logger.warn('unknown_event', { eventType: envelope.type });
  }
}

/**
 * Starts the consumer loop. Resolves when the topology is declared and the
 * consumer is registered.
 *
 * @param {object} deps
 * @param {UsuarioService} deps.service
 */
export async function iniciarConsumidor(service) {
  const connection = await conectarConBackoff();
  const channel = await connection.createChannel();
  let requeueDelay = REQUEUE_BACKOFF_INICIAL_MS;

  await channel.assertExchange(EXCHANGE, 'topic', { durable: true });
  await channel.assertQueue(QUEUE, { durable: true });
  for (const key of ROUTING_KEYS) {
    await channel.bindQueue(QUEUE, EXCHANGE, key);
  }
  channel.prefetch(1); // one at a time: ordering + backpressure

  await channel.consume(QUEUE, async (msg) => {
    if (!msg) return;
    const headers = (msg.properties && msg.properties.headers) || {};
    const parentContext = extractContext(headers);
    const span = tracer('auth-service').startSpan(
      'auth.consumir_evento',
      {
        attributes: {
          'messaging.system': 'rabbitmq',
          'messaging.destination': QUEUE,
          'messaging.operation': 'process',
        },
      },
      parentContext,
    );

    return context.with(trace.setSpan(parentContext, span), async () => {
      try {
        const envelope = JSON.parse(msg.content.toString());
        const eventoId = envelope && envelope.id;
        span.setAttribute('event.id', String(eventoId || ''));
        span.setAttribute('event.type', String((envelope && envelope.type) || ''));
        if (!eventoId) {
          // Poison message: cannot dedup or apply; drop it with ACK.
          logger.warn('event_without_id');
          channel.ack(msg);
          return;
        }
        if (await service.store.procesados(eventoId)) {
          logger.info('duplicate_event', { eventId: eventoId });
          channel.ack(msg);
          return;
        }
        await aplicarEvento(service, envelope);
        await service.store.marcarProcesado(eventoId);
        requeueDelay = REQUEUE_BACKOFF_INICIAL_MS;
        channel.ack(msg);
      } catch (err) {
        logger.error('event_processing_failed', { error: err.message });
        channel.nack(msg, false, true);
        await sleep(requeueDelay);
        requeueDelay = Math.min(requeueDelay * 2, REQUEUE_BACKOFF_MAX_MS);
      } finally {
        span.end();
      }
    });
  });

  // eslint-disable-next-line no-console
  logger.info('consumer_ready', {
    queue: QUEUE,
    exchange: EXCHANGE,
    routingKeys: ROUTING_KEYS,
  });
  return { connection, channel };
}

/**
 * Builds the event publisher injected into UsuarioService. Every envelope
 * follows CATALOGO_EVENTOS.md §1: UUID id, routing key = type, version 1.0,
 * UTC ISO occurredAt, producer auth-service, non-null data.
 */
export function crearPublicadorEventos(getChannel) {
  return async function publishEvent(type, data) {
    const channel = typeof getChannel === 'function' ? getChannel() : getChannel;
    if (!channel) {
      throw new Error('Canal RabbitMQ no disponible todavía');
    }
    const envelope = {
      id: randomUUID(),
      type,
      version: '1.0',
      occurredAt: new Date().toISOString(),
      producer: 'auth-service',
      data,
    };
    channel.publish(EXCHANGE, type, Buffer.from(JSON.stringify(envelope)), {
      persistent: true,
      // Reto 8: propaga W3C traceparent/tracestate/baggage en AMQP.
      headers: injectContext({}),
    });
    recordEventoPublicado(type);
    logger.info('event_published', { eventType: type, eventId: envelope.id });
  };
}

/** Real broker probe for /health. */
export async function verificarBroker(channel) {
  if (!channel) return 'DOWN';
  await channel.checkQueue(QUEUE);
  return 'UP';
}
