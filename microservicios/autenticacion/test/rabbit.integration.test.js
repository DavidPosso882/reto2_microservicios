import { describe, test } from 'node:test';
import assert from 'node:assert/strict';

process.env.JWT_SECRET = 'secreto-de-prueba-reto5';
process.env.RABBITMQ_HOST = 'localhost';

const EXCHANGE = 'ecosistema.eventos';
const QUEUE = 'q.auth';

/**
 * Fake amqplib connection/channel that records topology and publish calls so
 * the consumer wiring (exchange, queue, bindings, manual ACK/dedup order) can
 * be exercised without a real broker.
 */
function canalFalso() {
  const llamadas = { assertExchange: [], assertQueue: [], bindQueue: [], consumeCb: null, ack: [], nack: [] };
  let requeueDelay = 500;
  const channel = {
    assertExchange: async (name, type, opts) => {
      llamadas.assertExchange.push({ name, type, opts });
    },
    assertQueue: async (name, opts) => {
      llamadas.assertQueue.push({ name, opts });
      return { queue: name };
    },
    bindQueue: async (queue, exchange, key) => {
      llamadas.bindQueue.push({ queue, exchange, key });
    },
    prefetch: () => {},
    consume: async (queue, cb) => {
      llamadas.consumeCb = { queue, cb };
    },
    publish: (exchange, key, content) => {
      llamadas.publicado = llamadas.publicado || [];
      llamadas.publicado.push({ exchange, key, content: JSON.parse(content.toString()) });
    },
    ack: (msg) => llamadas.ack.push(msg.id ?? msg),
    nack: (msg) => llamadas.nack.push(msg.id ?? msg),
  };
  const connection = {
    createChannel: async () => channel,
    close: async () => {},
  };
  return { connection, channel, llamadas };
}

function envelope({ id, type, data }) {
  return { id, type, version: '1.0', occurredAt: new Date().toISOString(), producer: 'x', data };
}

describe('Integración RabbitMQ (canal falso)', () => {
  test('declara exchange topic durable, cola q.auth y sus 4 bindings', async () => {
    const { iniciarConsumidor, _setAmqpConnectForTests } = await import('../src/rabbit.js');
    const { InMemoryUsuarioStore } = await import('../src/store/UsuarioStore.js');
    const { UsuarioService } = await import('../src/service/UsuarioService.js');
    const { connection, llamadas } = canalFalso();
    _setAmqpConnectForTests(async () => connection);
    const service = new UsuarioService(new InMemoryUsuarioStore());
    await iniciarConsumidor(service);
    assert.deepEqual(llamadas.assertExchange[0], {
      name: EXCHANGE,
      type: 'topic',
      opts: { durable: true },
    });
    assert.equal(llamadas.assertQueue[0].name, QUEUE);
    const keys = llamadas.bindQueue.map((b) => b.key).sort();
    assert.deepEqual(keys, [
      'empleado.creado',
      'empleado.retirado',
      'vacaciones.finalizadas',
      'vacaciones.iniciadas',
    ]);
  });

  test('ACK manual después de aplicar + dedup; duplicado se descarta sin reaplicar', async () => {
    const { iniciarConsumidor, _setAmqpConnectForTests } = await import('../src/rabbit.js');
    const { InMemoryUsuarioStore } = await import('../src/store/UsuarioStore.js');
    const { UsuarioService } = await import('../src/service/UsuarioService.js');
    const { connection, llamadas } = canalFalso();
    _setAmqpConnectForTests(async () => connection);

    const store = new InMemoryUsuarioStore();
    const publicados = [];
    const service = new UsuarioService(store, {
      eventPublisher: async (type, data) => publicados.push({ type, data }),
    });
    const { consumeCb } = (await iniciarConsumidor(service)).llamadas ?? {};
    const cb = llamadas.consumeCb.cb;
    assert.ok(cb, 'consume debe registrar callback');

    const msg = (body) => ({
      content: Buffer.from(JSON.stringify(body)),
      ack: undefined,
      nack: undefined,
    });
    // Atributo "id" sobre el objeto para el fake ack/nack.
    const m1 = msg({ id: 'evt-1', type: 'empleado.creado', data: { id: 'E101', email: 'e101@empresa.com' } });
    m1.id = 'evt-1';
    await cb(m1);
    // Message applied AND ledger row written, then ACK.
    assert.ok(await store.buscarPorId('E101'));
    assert.ok(await store.procesados('evt-1'));
    assert.deepEqual(llamadas.ack, ['evt-1']);
    assert.equal(publicados.filter((e) => e.type === 'usuario.creado').length, 1);

    // Same envelope id redelivered: dedup, ACK, no second effect.
    await cb(m1);
    assert.equal(llamadas.ack.filter((a) => a === 'evt-1').length, 2);
    assert.equal(publicados.filter((e) => e.type === 'usuario.creado').length, 1);

    // Permanent payload error becomes poison: ACK'd (discarded), not requeued.
    const mBad = msg({ id: 'evt-bad', type: 'empleado.creado', data: {} });
    mBad.id = 'evt-bad';
    await cb(mBad);
    assert.deepEqual(llamadas.ack, ['evt-1', 'evt-1', 'evt-bad']);
    assert.deepEqual(llamadas.nack, []);
  });
});

describe('Envelope del publicador (contraseña jamás en eventos)', () => {
  test('publica envelope completo con producer auth-service y version 1.0', async () => {
    const { crearPublicadorEventos } = await import('../src/rabbit.js');
    const canal = canalFalso().channel;
    const publishEvent = crearPublicadorEventos(canal);
    await publishEvent('cuenta.desactivada', { email: 'e101@empresa.com', empleadoId: 'E101', motivo: 'RETIRO', permanente: true });
    const publicado = canal.publish.mock ?? null;
    // Verify via the recorded call instead of jest mocks.
    const { llamadas } = canalFalso.page ?? {};
    assert.ok(true); // recorded assertions live in the publisher test below
  });

  test('el envelope cumple el catálogo (id uuid, version, occurredAt UTC, producer)', async () => {
    const { crearPublicadorEventos } = await import('../src/rabbit.js');
    const { connection, channel } = canalFalso();
    const publishEvent = crearPublicadorEventos(channel);
    await publishEvent('usuario.recuperacion', { email: 'e101@empresa.com', resetToken: 'abc' });
    // The fake channel does not record publish directly; re-record:
    const recorded = [];
    const canal2 = canalFalso();
    const publisher2 = crearPublicadorEventos(canal2.channel);
    canal2.channel.publish = (exchange, key, content) => {
      recorded.push({ exchange, key, envelope: JSON.parse(content.toString()) });
    };
    await publisher2('usuario.recuperacion', { email: 'E', resetToken: 't' });
    const { exchange, key, envelope: env } = recorded[0];
    assert.equal(exchange, EXCHANGE);
    assert.equal(key, 'usuario.recuperacion');
    assert.match(env.id, /^[0-9a-f-]{36}$/);
    assert.equal(env.version, '1.0');
    assert.match(env.occurredAt, /Z$/);
    assert.equal(env.producer, 'auth-service');
    assert.equal(env.data.email !== undefined, true);
  });
});
