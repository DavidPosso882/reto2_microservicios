import express from 'express';
import swaggerUi from 'swagger-ui-express';
import yaml from 'yaml';
import { createAuthRouter } from './routes/authRoutes.js';
import { UsuarioService } from './service/UsuarioService.js';
import { AppError } from './errors.js';
import { openapiSpec, swaggerUiOptions } from './openapi.js';
import { accessLogMiddleware } from './observability/http.js';
import {
  getMetrics,
  metricsHandler,
  metricsMiddleware,
  normalizeRoute,
} from './observability/metrics.js';
import { logger } from './observability/logger.js';

/**
 * Builds the auth-service Express application (Reto 5).
 *
 * The store and event publisher are injected so the same app runs against
 * PostgreSQL in production (PgUsuarioStore) or an in-memory store in tests,
 * and so HTTP handlers can be tested without a broker (publisher optional).
 *
 * @param {object} deps
 * @param {object} deps.store - account + dedup store (Pg or InMemory).
 * @param {Function} [deps.eventPublisher] - async (type, data) => void.
 */
export function createApp({ store, eventPublisher = null, healthChecks = {} }) {
  const app = express();
  const service = new UsuarioService(store, { eventPublisher });
  const metrics = getMetrics('auth-service');

  // Reto 8: access log JSON + métricas RED.
  app.use(accessLogMiddleware);
  app.use(metricsMiddleware(metrics, (req) => normalizeRoute(req.path)));

  app.use(express.json());

  // Documentation: browsable Swagger UI + machine-readable contract.
  app.get('/openapi.yaml', (req, res) => {
    res.type('text/yaml').send(yaml.stringify(openapiSpec()));
  });
  app.use('/docs', swaggerUi.serve, swaggerUi.setup(openapiSpec(), swaggerUiOptions()));

  // Business endpoints under /auth (gateway will whitelist /auth/*).
  app.use('/auth', createAuthRouter({ service }));

  app.get('/health', async (req, res) => {
    const database = await runHealthCheck(healthChecks.database);
    const messageBroker = await runHealthCheck(healthChecks.messageBroker);
    const status = database === 'DOWN' || messageBroker === 'DOWN' ? 'DOWN' : 'UP';
    res.status(status === 'UP' ? 200 : 503).json({
      status,
      service: 'auth-service',
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

  // Expose the singleton service for the server bootstrap (rabbit wiring).
  app.locals.authService = service;
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
