import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';

/**
 * Builds the API Gateway application (Reto 3).
 *
 * The gateway is a pure reverse proxy: it routes by path prefix and never
 * contains business logic. Bodies, headers, query strings and status codes
 * travel untouched between the client and the upstream service.
 *
 * Routing:
 *   /empleados*      -> empleados-service
 *   /departamentos*  -> departamentos-service
 *
 * Upstream URLs are injected so tests can point at fake servers while
 * production (docker-compose) points at the Docker service names.
 *
 * @param {object} opts
 * @param {string} opts.empleadosUrl - base URL of empleados-service (no trailing path).
 * @param {string} opts.departamentosUrl - base URL of departamentos-service (no trailing path).
 * @returns {import('express').Express}
 */
export function createGateway({ empleadosUrl, departamentosUrl }) {
  const app = express();

  // Own health check: proves the edge itself is alive, independently of upstreams.
  app.get('/health', (req, res) => {
    res.status(200).json({ status: 'ok', service: 'api-gateway' });
  });

  // When the destination does not answer (down, refused, timeout), answer 503
  // with the house JSON envelope instead of leaking a framework error page.
  const proxyErrorHandler = (servicio) => (err, req, res) => {
    if (res.headersSent) {
      return;
    }
    res.status(503).json({
      status: 503,
      error: `El servicio de ${servicio} no está disponible en este momento`,
    });
  };

  const proxyOptions = (target, servicio, prefijo) => ({
    target,
    changeOrigin: true,
    // Express strips the mount prefix before the middleware runs, so the
    // upstream would receive '/E001' instead of '/empleados/E001'.
    // Re-attach it: internal routes stay exactly as in Reto 2.
    pathRewrite: (path) => (path === '/' ? `/${prefijo}` : `/${prefijo}${path}`),
    // Must outlive empleados worst case (retries + backoff before its fallback, ~15s).
    proxyTimeout: 30000,
    timeout: 30000,
    on: {
      error: proxyErrorHandler(servicio),
    },
  });

  // NOTE: no express.json() before the proxies on purpose: parsing the body
  // here would consume the stream and the upstream would receive an empty body.
  // The proxy forwards the raw request untouched.
  app.use('/empleados', createProxyMiddleware(proxyOptions(empleadosUrl, 'empleados', 'empleados')));
  app.use(
    '/departamentos',
    createProxyMiddleware(proxyOptions(departamentosUrl, 'departamentos', 'departamentos')),
  );

  // Unknown routes -> 404 envelope (same contract as the business services).
  app.use((req, res) => {
    res.status(404).json({ status: 404, error: 'Recurso no encontrado' });
  });

  // Centralized error handler -> JSON envelope, never a stack trace.
  // eslint-disable-next-line no-unused-vars
  app.use((err, req, res, next) => {
    if (res.headersSent) {
      return;
    }
    const status = err.status || 500;
    const message =
      status >= 500 ? 'Error interno del servidor' : err.message || 'Error interno del servidor';
    res.status(status).json({ status, error: message });
  });

  return app;
}
