import client from 'prom-client';

/**
 * One registry per process. collectDefaultMetrics installs an interval, so it
 * must run only once even when tests build several app instances.
 */
let cached = null;

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

  cached = { registry, httpRequests, httpDuration };
  return cached;
}

/** Groups dynamic segments so labels stay bounded. */
export function normalizeRoute(path = '/') {
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
