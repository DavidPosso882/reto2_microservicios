import client from 'prom-client';

/**
 * One registry per process. collectDefaultMetrics installs an interval, so it
 * must run only once even when tests build several app instances.
 */
let cached = null;

/** Eventos que publica auth-service (CATALOGO_EVENTOS.md). */
const EVENTOS_AUTH = ['usuario.creado', 'usuario.recuperacion', 'cuenta.activada', 'cuenta.desactivada'];

export function getMetrics(service) {
  if (cached) return cached;

  const registry = new client.Registry();
  registry.setDefaultLabels({ service });
  client.collectDefaultMetrics({ register: registry, prefix: '' });

  const httpRequests = new client.Counter({
    name: 'http_requests_total',
    help: 'Total de peticiones HTTP por metodo, ruta y codigo',
    labelNames: ['method', 'route', 'code'],
    registers: [registry],
  });

  const httpDuration = new client.Histogram({
    name: 'http_request_duration_seconds',
    help: 'Duracion de peticiones HTTP en segundos',
    labelNames: ['method', 'route', 'code'],
    buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
    registers: [registry],
  });

  // Proyecto Final — métrica de negocio: usuario.creado, cuenta.activada,
  // cuenta.desactivada, usuario.recuperacion (mismo nombre que empleados y
  // vacaciones para agregarlas en un solo panel de Grafana).
  const eventosPublicados = new client.Counter({
    name: 'eventos_publicados_total',
    help: 'Eventos publicados al broker por routing key',
    labelNames: ['routing_key'],
    registers: [registry],
  });
  // Series en 0 desde el arranque: sin esto el primer evento de cada tipo
  // crea la serie ya en 1 y increase() de Prometheus no lo cuenta.
  for (const routingKey of EVENTOS_AUTH) {
    eventosPublicados.inc({ routing_key: routingKey }, 0);
  }

  cached = { registry, httpRequests, httpDuration, eventosPublicados };
  return cached;
}

/** Cuenta un evento publicado (el registro ya existe o se crea con el nombre del servicio). */
export function recordEventoPublicado(routingKey) {
  getMetrics('auth-service').eventosPublicados.inc({ routing_key: routingKey });
}

/**
 * Groups dynamic segments so labels stay bounded.
 *
 * Accepts a path string or the Express request: metricsMiddleware calls the
 * resolver with `req`, and calling `.replace` on the request object threw
 * inside the 'finish' handler, crashing auth-service after its first request.
 */
export function normalizeRoute(input = '/') {
  const path = typeof input === 'string' ? input : (input && input.path) || '/';
  return path
    .replace(/\/V-\d{4}-\d{4}/g, '/:id')
    .replace(/\/[A-Z]\d{3,}/g, '/:id')
    .replace(/\/[0-9a-f-]{36}/gi, '/:id');
}

/** First path segment (gateway: /empleados, /auth, ...). */
export function gatewayRoute(req) {
  const segment = (req.path || '/').split('/').filter(Boolean)[0];
  return segment ? `/${segment}` : '/';
}

export function metricsMiddleware(metrics, routeResolver = normalizeRoute) {
  return (req, res, next) => {
    if (req.path === '/metrics') return next();
    const started = process.hrtime.bigint();
    res.on('finish', () => {
      const seconds = Number(process.hrtime.bigint() - started) / 1e9;
      const labels = {
        method: req.method,
        route: routeResolver(req),
        code: String(res.statusCode),
      };
      metrics.httpRequests.inc(labels);
      metrics.httpDuration.observe(labels, seconds);
    });
    return next();
  };
}

export async function metricsHandler(metrics, req, res) {
  res.set('Content-Type', metrics.registry.contentType);
  res.end(await metrics.registry.metrics());
}
