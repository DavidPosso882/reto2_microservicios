import 'dotenv/config';
import { startTelemetry, shutdownTelemetry } from './observability/telemetry.js';
import { logger } from './observability/logger.js';

// Reto 8: telemetría antes de cargar express/pg/amqplib para que la
// auto-instrumentación parchee esos módulos.
startTelemetry('auth-service');

const { createPool } = await import('./config/db.js');
const { PgUsuarioStore } = await import('./store/UsuarioStore.js');
const { createApp } = await import('./app.js');
const { iniciarConsumidor, crearPublicadorEventos, verificarBroker } = await import(
  './rabbit.js'
);

const port = Number(process.env.PORT || 8086);

const pool = createPool();
const store = new PgUsuarioStore(pool);

let consumerChannel = null;
let consumerConnection = null;

// App first (HTTP readiness does not depend on the broker); the service lives
// in app.locals so app.js stays the single wiring point.
const app = createApp({
  store,
  healthChecks: {
    database: () => checkDatabase(pool),
    messageBroker: () => verificarBroker(consumerChannel),
  },
});
const service = app.locals.authService;

const server = app.listen(port, () => {
  logger.info('auth_service_listening', { port });
  logger.info('auth_service_docs', { url: `http://localhost:${port}/docs` });

  iniciarConsumidor(service)
    .then(({ connection, channel }) => {
      consumerConnection = connection;
      consumerChannel = channel;
      service.setEventPublisher(crearPublicadorEventos(() => channel));
      logger.info('auth_rabbit_ready');
    })
    .catch((err) => {
      logger.error('auth_rabbit_unavailable', { error: err.message });
      process.exit(1);
    });
});

/** Real DB probe with a bounded timeout (health must never hang). */
async function checkDatabase(poolToCheck) {
  let timer;
  try {
    await Promise.race([
      (async () => {
        const client = await poolToCheck.connect();
        try {
          await client.query('SELECT 1');
        } finally {
          client.release();
        }
      })(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('db health timeout')), 2000);
      }),
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function shutdown(signal) {
  logger.info('shutdown_started', { signal });
  server.close(async () => {
    try {
      if (consumerChannel) await consumerChannel.close();
      if (consumerConnection) await consumerConnection.close();
      await pool.end();
    } catch (err) {
      logger.warn('shutdown_cleanup_failed', { error: err.message });
    }
    await shutdownTelemetry();
    logger.info('shutdown_completed', { signal });
    process.exit(0);
  });
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
