import express from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { authenticate, authorizeService, forwardIdentity } from './middleware/auth.js';

/**
 * Builds the API Gateway application (Reto 3).
 *
 * The gateway is a pure reverse proxy: it routes by path prefix and never
 * contains business logic. Bodies, headers, query strings and status codes
 * travel untouched between the client and the upstream service.
 *
 * Routing (negocio, con re-attach del prefijo porque el upstream espera /empleados, /departamentos...):
 *   /empleados*      -> empleados-service
 *   /departamentos*  -> departamentos-service
 *   /perfiles*       -> perfiles-service (Reto 4)
 *   /notificaciones* -> notificaciones-service (Reto 4)
 *   /vacaciones*     -> vacaciones-service (Reto 4)
 *
 * Auth (Reto 5, JWT validado SOLO en el gateway):
 *   /auth/login, /auth/recover-password, /auth/reset-password y
 *   /auth/bootstrap se proxyean en claro (necesitan llegar sin token: son el
 *   login y la recuperación de cuenta) y se montan ANTES del middleware de
 *   autenticación.
 *   El resto de /auth/* (change-password) y los cinco servicios de negocio
 *   exigen Bearer JWT válido (HS256 + JWT_SECRET compartido con auth-service)
 *   y RBAC: ADMIN escribe todo; USER solo lee, salvo su propio perfil
 *   (PUT /perfiles/:empleadoId) — 401 sin token, 403 con token insuficiente.
 *   En change-password el gateway reescribe X-User-Id/X-User-Role con la
 *   identidad verificada (auth-service las usa en lugar de duplicar la
 *   validación del JWT).
 *
 * Docs (Swagger UI / OpenAPI, SIN re-attach porque el upstream sirve docs en raiz):
 * se montan ANTES del negocio y quitan el prefijo del gateway:
 *   /departamentos/api-docs* -> /api-docs* (swagger-ui-express)
 *   /empleados/swagger-ui.html, /empleados/swagger-ui*, /empleados/v3/api-docs* -> idem en raiz (springdoc)
 *   /notificaciones/docs, /redoc, /openapi.json -> /docs, /redoc, /openapi.json (FastAPI con root_path)
 *   /perfiles/openapi.yaml, /perfiles/docs -> /openapi.yaml, /docs (Go, docs propios)
 *   /vacaciones/openapi.yaml, /vacaciones/docs -> /openapi.yaml, /docs (Ruby, docs propios)
 *
 * Upstream URLs are injected so tests can point at fake servers while
 * production (docker-compose) points at the Docker service names.
 *
 * @param {object} opts
 * @param {string} opts.empleadosUrl - base URL of empleados-service (no trailing path).
 * @param {string} opts.departamentosUrl - base URL of departamentos-service (no trailing path).
 * @param {string} opts.perfilesUrl - base URL of perfiles-service (no trailing path).
 * @param {string} opts.notificacionesUrl - base URL of notificaciones-service (no trailing path).
 * @param {string} opts.vacacionesUrl - base URL of vacaciones-service (no trailing path).
 * @param {string} opts.authUrl - base URL of auth-service (no trailing path).
 * @returns {import('express').Express}
 */
export function createGateway({
  empleadosUrl,
  departamentosUrl,
  perfilesUrl,
  notificacionesUrl,
  vacacionesUrl,
  authUrl,
}) {
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
    // Covers both the bare prefix ('/' after mount) and the prefix with a
    // query string but no subpath ('/?query' after mount).
    pathRewrite: (path) => {
      if (path === '/') return `/${prefijo}`;
      if (path.startsWith('/?')) return `/${prefijo}${path.slice(1)}`;
      return `/${prefijo}${path}`;
    },
    // Must outlive empleados worst case (retries + backoff before its fallback, ~15s).
    proxyTimeout: 30000,
    timeout: 30000,
    on: {
      error: proxyErrorHandler(servicio),
    },
  });

  // Docs proxies: strip the gateway prefix because upstreams serve docs at root.
  // MUST be mounted BEFORE the business proxies (Express matches in order).
  // Uses req.originalUrl (full path) so it does not depend on Express stripping.
  const docsRewrite = (gatewayPrefix, upstreamBase) => (path, req) => {
    const orig = (req && req.originalUrl) || path || '/';
    const qmark = orig.indexOf('?');
    const pathname = qmark === -1 ? orig : orig.slice(0, qmark);
    const search = qmark === -1 ? '' : orig.slice(qmark);
    let rest = pathname.startsWith(gatewayPrefix)
      ? pathname.slice(gatewayPrefix.length)
      : pathname;
    if (rest === '') rest = '/';
    const base = upstreamBase.endsWith('/') ? upstreamBase.slice(0, -1) : upstreamBase;
    let upstreamPath;
    if (rest === '/') {
      // Bare docs URL: swagger-ui-express EXIGE trailing (/api-docs -> 301 a /api-docs/).
      // FastAPI/Go/Ruby exigen lo contrario (/docs/ -> 307 a /docs). Diferenciar por base.
      upstreamPath = base === '/api-docs' ? `${base}/` : base;
    } else {
      upstreamPath = `${base}${rest.startsWith('/') ? rest : `/${rest}`}`;
    }
    return `${upstreamPath}${search}`;
  };

  // Reescribe redirects del upstream (Location: /swagger-ui/... ) para no perder el prefijo.
  // Sin esto el navegador sigue a /swagger-ui/... pelado y el gateway devuelve 404.
  const docsLocationRewrite = (gatewayPrefix) => (proxyRes, req) => {
    const loc = proxyRes.headers && proxyRes.headers.location;
    if (typeof loc !== 'string' || !loc.startsWith('/')) return;
    const serviceRoot = `/${gatewayPrefix.split('/')[1]}`;
    if (loc === serviceRoot || loc.startsWith(`${serviceRoot}/`)) return;
    proxyRes.headers.location = `${serviceRoot}${loc}`;
  };

  const docsProxy = (target, servicio, gatewayPrefix, upstreamBase) => ({
    target,
    changeOrigin: true,
    pathRewrite: docsRewrite(gatewayPrefix, upstreamBase),
    proxyTimeout: 30000,
    timeout: 30000,
    on: {
      error: proxyErrorHandler(servicio),
      proxyRes: docsLocationRewrite(gatewayPrefix),
    },
  });

  // -- Departamentos (swagger-ui-express en /api-docs) --
  app.use(
    '/departamentos/api-docs',
    createProxyMiddleware(
      docsProxy(departamentosUrl, 'departamentos', '/departamentos/api-docs', '/api-docs'),
    ),
  );
  // -- Empleados (springdoc: /swagger-ui.html, /swagger-ui/*, /v3/api-docs/*) --
  app.use(
    '/empleados/swagger-ui.html',
    createProxyMiddleware(
      docsProxy(empleadosUrl, 'empleados', '/empleados/swagger-ui.html', '/swagger-ui.html'),
    ),
  );
  app.use(
    '/empleados/swagger-ui',
    createProxyMiddleware(
      docsProxy(empleadosUrl, 'empleados', '/empleados/swagger-ui', '/swagger-ui'),
    ),
  );
  app.use(
    '/empleados/v3/api-docs',
    createProxyMiddleware(
      docsProxy(empleadosUrl, 'empleados', '/empleados/v3/api-docs', '/v3/api-docs'),
    ),
  );
  // Fallback absoluto: el JS de springdoc pide /v3/api-docs/... y /swagger-ui/... sin prefijo.
  // Solo empleados usa esas raíces, así que exponerlas en el gateway es seguro y evita
  // el "Failed to load remote configuration" sin tocar el servicio.
  app.use(
    '/v3/api-docs',
    createProxyMiddleware(docsProxy(empleadosUrl, 'empleados', '/v3/api-docs', '/v3/api-docs')),
  );
  app.use(
    '/swagger-ui',
    createProxyMiddleware(docsProxy(empleadosUrl, 'empleados', '/swagger-ui', '/swagger-ui')),
  );
  // -- Notificaciones (FastAPI con root_path=/notificaciones) --
  app.use(
    '/notificaciones/docs',
    createProxyMiddleware(
      docsProxy(notificacionesUrl, 'notificaciones', '/notificaciones/docs', '/docs'),
    ),
  );
  app.use(
    '/notificaciones/redoc',
    createProxyMiddleware(
      docsProxy(notificacionesUrl, 'notificaciones', '/notificaciones/redoc', '/redoc'),
    ),
  );
  app.use(
    '/notificaciones/openapi.json',
    createProxyMiddleware(
      docsProxy(
        notificacionesUrl,
        'notificaciones',
        '/notificaciones/openapi.json',
        '/openapi.json',
      ),
    ),
  );
  // -- Perfiles (Go: YAML + /docs propio con CDN relativo) --
  app.use(
    '/perfiles/openapi.yaml',
    createProxyMiddleware(
      docsProxy(perfilesUrl, 'perfiles', '/perfiles/openapi.yaml', '/openapi.yaml'),
    ),
  );
  app.use(
    '/perfiles/docs',
    createProxyMiddleware(docsProxy(perfilesUrl, 'perfiles', '/perfiles/docs', '/docs')),
  );
  // -- Vacaciones (Ruby: YAML + /docs propio con CDN relativo) --
  app.use(
    '/vacaciones/openapi.yaml',
    createProxyMiddleware(
      docsProxy(vacacionesUrl, 'vacaciones', '/vacaciones/openapi.yaml', '/openapi.yaml'),
    ),
  );
  app.use(
    '/vacaciones/docs',
    createProxyMiddleware(
      docsProxy(vacacionesUrl, 'vacaciones', '/vacaciones/docs', '/docs'),
    ),
  );

  // -- Auth público (login y ciclo de vida de cuenta SIN token) --
  // Montados ANTES del middleware de autenticación: el host necesita alcanzar
  // login/recover/reset/bootstrap sin credencial, y ahora el gateway es la
  // única puerta hacia auth-service (su puerto :8086 ya no se publica al host).
  //
  // Montaje por ruta EXACTA: el strip de Express deja '' en la ruta justa, así
  // que se re-adjunta el upstream path completo (misma lógica que los docs).
  const singlePathProxy = (target, servicio, upstreamPath) => ({
    target,
    changeOrigin: true,
    pathRewrite: docsRewrite(upstreamPath, upstreamPath),
    proxyTimeout: 30000,
    timeout: 30000,
    on: {
      error: proxyErrorHandler(servicio),
    },
  });

  app.use(
    '/auth/login',
    createProxyMiddleware(singlePathProxy(authUrl, 'auth', '/auth/login')),
  );
  app.use(
    '/auth/recover-password',
    createProxyMiddleware(singlePathProxy(authUrl, 'auth', '/auth/recover-password')),
  );
  app.use(
    '/auth/reset-password',
    createProxyMiddleware(singlePathProxy(authUrl, 'auth', '/auth/reset-password')),
  );
  app.use(
    '/auth/bootstrap',
    createProxyMiddleware(singlePathProxy(authUrl, 'auth', '/auth/bootstrap')),
  );

  // A partir de aquí TODO exige Bearer JWT válido (401 con envoltorio propio).
  app.use(authenticate);

  // -- Auth protegido: change-password. La identidad ya fue verificada por el
  // gateway; se reenvía como cabeceras confiables que auth-service consume
  // (y sobreescribe las que el cliente pudiera haber falsificado).
  app.use(
    '/auth',
    forwardIdentity,
    createProxyMiddleware(proxyOptions(authUrl, 'auth', 'auth')),
  );

  // NOTE: no express.json() before the proxies on purpose: parsing the body
  // here would consume the stream and the upstream would receive an empty body.
  // The proxy forwards the raw request untouched.
  // Negocio: RBAC/propiedad ANTES de tocar el upstream; el re-attach del
  // prefijo interno queda intacto (propio del Reto 3).
  app.use(
    '/empleados',
    authorizeService('empleados'),
    createProxyMiddleware(proxyOptions(empleadosUrl, 'empleados', 'empleados')),
  );
  app.use(
    '/departamentos',
    authorizeService('departamentos'),
    createProxyMiddleware(proxyOptions(departamentosUrl, 'departamentos', 'departamentos')),
  );
  app.use(
    '/perfiles',
    authorizeService('perfiles'),
    createProxyMiddleware(proxyOptions(perfilesUrl, 'perfiles', 'perfiles')),
  );
  app.use(
    '/notificaciones',
    authorizeService('notificaciones'),
    createProxyMiddleware(proxyOptions(notificacionesUrl, 'notificaciones', 'notificaciones')),
  );
  app.use(
    '/vacaciones',
    authorizeService('vacaciones'),
    createProxyMiddleware(proxyOptions(vacacionesUrl, 'vacaciones', 'vacaciones')),
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
