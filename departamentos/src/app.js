import express from 'express';
import swaggerUi from 'swagger-ui-express';
import { createDepartamentoRouter } from './routes/departamentoRoutes.js';
import { DepartamentoService } from './service/DepartamentoService.js';
import { AppError } from './errors.js';
import { buildSwaggerSpec } from './swagger.js';
import { accessLogMiddleware } from './observability/http.js';
import {
  departamentosRoute,
  getMetrics,
  metricsHandler,
  metricsMiddleware,
} from './observability/metrics.js';
import { logger } from './observability/logger.js';

/**
 * Builds the Express application.
 *Prueba 3 pipeline
 * The store is injected so the same app can run against PostgreSQL in
 * production (PgDepartamentoStore) or an in-memory store in tests.
 *
 * @param {object} deps
 * @param {object} deps.store - store implementing create/findById/findAll.
 * @returns {import('express').Express}
 */
export function createApp({ store, healthChecks = {} }) {
  const app = express();
  const service = new DepartamentoService(store);
  const metrics = getMetrics('departamentos-service');

  // Reto 8: access log JSON + métricas RED.
  app.use(accessLogMiddleware);
  app.use(metricsMiddleware(metrics, departamentosRoute));

  app.use(express.json());

  // Swagger UI documentation.
  app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(buildSwaggerSpec()));

  // Business endpoints.
  app.use('/departamentos', createDepartamentoRouter(service));

  // Reto 8: health real (DB) + métricas Prometheus.
  app.get('/health', async (req, res) => {
    const database = await runHealthCheck(healthChecks.database);
    const messageBroker = 'N/A';
    const status = database === 'DOWN' ? 'DOWN' : 'UP';
    res.status(status === 'UP' ? 200 : 503).json({
      status,
      service: 'departamentos-service',
      checks: { database, messageBroker },
    });
  });

  app.get('/metrics', (req, res) => metricsHandler(metrics, req, res));

  // Unknown routes -> 404 envelope.
  app.use((req, res) => {
    res.status(404).json({ status: 404, error: 'Recurso no encontrado' });
  });

  // Centralized error handler -> JSON envelope.
  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    const status = err instanceof AppError ? err.status : err.status || 500;
    const message = err instanceof AppError ? err.message : 'Error interno del servidor';

    if (status >= 500) {
      // eslint-disable-next-line no-console
      logger.error('internal_error', { error: err.message });
    }

    res.status(status).json({ status, error: message });
  });

  return app;
}

/** Runs a health probe, mapping missing/throw to N/A/DOWN respectively. */
async function runHealthCheck(check) {
  if (typeof check !== 'function') return 'N/A';
  try {
    await check();
    return 'UP';
  } catch (err) {
    logger.warn('health_check_failed', { error: err.message });
    return 'DOWN';
  }
}
