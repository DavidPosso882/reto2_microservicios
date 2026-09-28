import express from 'express';
import swaggerUi from 'swagger-ui-express';
import yaml from 'yaml';
import { createAuthRouter } from './routes/authRoutes.js';
import { UsuarioService } from './service/UsuarioService.js';
import { AppError } from './errors.js';
import { openapiSpec, swaggerUiOptions } from './openapi.js';

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
export function createApp({ store, eventPublisher = null }) {
  const app = express();
  const service = new UsuarioService(store, { eventPublisher });

  app.use(express.json());

  // Documentation: browsable Swagger UI + machine-readable contract.
  app.get('/openapi.yaml', (req, res) => {
    res.type('text/yaml').send(yaml.stringify(openapiSpec()));
  });
  app.use('/docs', swaggerUi.serve, swaggerUi.setup(openapiSpec(), swaggerUiOptions()));

  // Business endpoints under /auth (gateway will whitelist /auth/*).
  app.use('/auth', createAuthRouter({ service }));

  app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok', service: 'auth-service' });
  });

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
      console.error(err);
    }

    res.status(status).json({ status, error: message });
  });

  // Expose the singleton service for the server bootstrap (rabbit wiring).
  app.locals.authService = service;
  return app;
}
