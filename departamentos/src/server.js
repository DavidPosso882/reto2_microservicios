import 'dotenv/config';
import { startTelemetry, shutdownTelemetry } from './observability/telemetry.js';
import { logger } from './observability/logger.js';

// Reto 8: telemetría antes de cargar express/pg.
startTelemetry('departamentos-service');

const { createPool } = await import('./config/db.js');
const { PgDepartamentoStore } = await import('./store/PgDepartamentoStore.js');
const { createApp } = await import('./app.js');

const port = Number(process.env.PORT || 8082);

const pool = createPool();
const store = new PgDepartamentoStore(pool);
const app = createApp({
  store,
  healthChecks: { database: () => checkDatabase(pool) },
});

const server = app.listen(port, () => {
  logger.info('departamentos_service_listening', { port });
  logger.info('departamentos_service_docs', {
    url: `http://localhost:${port}/api-docs`,
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
