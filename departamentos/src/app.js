import express from 'express';
import swaggerUi from 'swagger-ui-express';
import { createDepartamentoRouter } from './routes/departamentoRoutes.js';
import { DepartamentoService } from './service/DepartamentoService.js';
import { AppError } from './errors.js';
import { buildSwaggerSpec } from './swagger.js';

/**
 * Builds the Express application.
 *
 * The store is injected so the same app can run against PostgreSQL in
 * production (PgDepartamentoStore) or an in-memory store in tests.
 *
 * @param {object} deps
 * @param {object} deps.store - store implementing create/findById/findAll.
 * @returns {import('express').Express}
 */
export function createApp({ store }) {
  const app = express();
  const service = new DepartamentoService(store);

  app.use(express.json());

  // Swagger UI documentation.
  app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(buildSwaggerSpec()));

  // Business endpoints.
  app.use('/departamentos', createDepartamentoRouter(service));

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

  return app;
}
