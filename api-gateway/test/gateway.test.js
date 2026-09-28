import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import jwt from 'jsonwebtoken';
import { createGateway } from '../src/app.js';

/**
 * Gateway contract tests (Reto 3/4) with fake upstreams, plus the JWT edge
 * security contract (Reto 5, Step 2).
 *
 * No Docker needed: tiny http servers stand in for empleados-service,
 * departamentos-service and auth-service, so routing, propagation, the 503
 * envelope and the 401/403 RBAC answers are verified in milliseconds.
 */

// The gateway reads JWT_SECRET lazily per request; tests point it at the same
// secret the "auth-service" signer below uses (HS256, shared by design).
const TEST_JWT_SECRET = 'secreto-compartido-api-gateway';

/** Signs an access token the way auth-service does ({ sub, role }, HS256). */
function bearer({ sub = 'E001', role = 'ADMIN', expiresIn = '10m', ...extra } = {}) {
  return jwt.sign({ sub, role, ...extra }, TEST_JWT_SECRET, {
    algorithm: 'HS256',
    expiresIn,
  });
}

const adminAuth = () => ({ authorization: `Bearer ${bearer()}` });
const userE009 = () => ({ authorization: `Bearer ${bearer({ sub: 'E009', role: 'USER' })}` });

function startEchoUpstream({ status = 200, body = null } = {}) {
  const requests = [];
  const server = http.createServer((req, res) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
    });
    req.on('end', () => {
      requests.push({
        method: req.method,
        url: req.url,
        headers: req.headers,
        body: raw,
      });
      const payload = body ?? { echoed: true };
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(payload));
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({
        server,
        requests,
        url: `http://127.0.0.1:${server.address().port}`,
      });
    });
  });
}

function listenEphemeral(app) {
  return new Promise((resolve) => {
    const server = app.listen(0, '127.0.0.1', () => {
      resolve({
        server,
        url: `http://127.0.0.1:${server.address().port}`,
      });
    });
  });
}

describe('api-gateway', () => {
  let empleados;
  let departamentos;
  let perfiles;
  let notificaciones;
  let vacaciones;
  let auth;
  let gateway;
  let gatewayDownstream;
  let gatewayVacacionesDown;
  let secretOriginal;

  before(async () => {
    secretOriginal = process.env.JWT_SECRET;
    process.env.JWT_SECRET = TEST_JWT_SECRET;
    empleados = await startEchoUpstream();
    departamentos = await startEchoUpstream();
    perfiles = await startEchoUpstream();
    notificaciones = await startEchoUpstream();
    vacaciones = await startEchoUpstream();
    auth = await startEchoUpstream();
    gateway = await listenEphemeral(
      createGateway({
        empleadosUrl: empleados.url,
        departamentosUrl: departamentos.url,
        perfilesUrl: perfiles.url,
        notificacionesUrl: notificaciones.url,
        vacacionesUrl: vacaciones.url,
        authUrl: auth.url,
      }),
    );
    // Gateway whose departamentos destination is unreachable (closed port 1).
    gatewayDownstream = await listenEphemeral(
      createGateway({
        empleadosUrl: empleados.url,
        departamentosUrl: 'http://127.0.0.1:1',
        perfilesUrl: perfiles.url,
        notificacionesUrl: notificaciones.url,
        vacacionesUrl: vacaciones.url,
        authUrl: auth.url,
      }),
    );
    // Gateway whose vacaciones destination is unreachable (closed port 1);
    // the other routes point at the real fake upstreams so only vacaciones fails.
    gatewayVacacionesDown = await listenEphemeral(
      createGateway({
        empleadosUrl: empleados.url,
        departamentosUrl: departamentos.url,
        perfilesUrl: perfiles.url,
        notificacionesUrl: notificaciones.url,
        vacacionesUrl: 'http://127.0.0.1:1',
        authUrl: auth.url,
      }),
    );
  });

  after(() => {
    empleados.server.close();
    departamentos.server.close();
    perfiles.server.close();
    notificaciones.server.close();
    vacaciones.server.close();
    auth.server.close();
    gateway.server.close();
    gatewayDownstream.server.close();
    gatewayVacacionesDown.server.close();
    if (secretOriginal === undefined) {
      delete process.env.JWT_SECRET;
    } else {
      process.env.JWT_SECRET = secretOriginal;
    }
  });

  it('expone su propio /health sin depender de los servicios', async () => {
    const res = await fetch(`${gateway.url}/health`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { status: 'ok', service: 'api-gateway' });
  });

  it('enruta /departamentos/* al servicio de departamentos preservando ruta y estado', async () => {
    const res = await fetch(`${gateway.url}/departamentos/IT`, { headers: adminAuth() });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(departamentos.requests.at(-1).url, '/departamentos/IT');
  });

  it('enruta /empleados/* al servicio de empleados preservando ruta', async () => {
    const res = await fetch(`${gateway.url}/empleados/E001`, { headers: adminAuth() });
    assert.equal(res.status, 200);
    assert.equal(empleados.requests.at(-1).url, '/empleados/E001');
  });

  it('propaga el cuerpo y las cabeceras en un POST sin alterarlos', async () => {
    const payload = { id: 'E009', nombre: 'Test' };
    const res = await fetch(`${gateway.url}/empleados`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-test': 'abc', ...adminAuth() },
      body: JSON.stringify(payload),
    });
    assert.equal(res.status, 200);
    const seen = empleados.requests.at(-1);
    assert.equal(seen.method, 'POST');
    assert.deepEqual(JSON.parse(seen.body), payload);
    assert.equal(seen.headers['x-test'], 'abc');
  });

  it('propaga el código de estado del servicio destino (404 intacto)', async () => {
    const failing = await startEchoUpstream({
      status: 404,
      body: { status: 404, error: 'El departamento con id X no existe' },
    });
    const gw = await listenEphemeral(
      createGateway({
        empleadosUrl: empleados.url,
        departamentosUrl: failing.url,
        perfilesUrl: perfiles.url,
        notificacionesUrl: notificaciones.url,
        vacacionesUrl: vacaciones.url,
        authUrl: auth.url,
      }),
    );
    try {
      const res = await fetch(`${gw.url}/departamentos/X`, { headers: adminAuth() });
      assert.equal(res.status, 404);
      assert.deepEqual(await res.json(), {
        status: 404,
        error: 'El departamento con id X no existe',
      });
    } finally {
      gw.server.close();
      failing.server.close();
    }
  });

  it('responde 503 con JSON descriptivo si el destino no responde', async () => {
    const res = await fetch(`${gatewayDownstream.url}/departamentos`, { headers: adminAuth() });
    assert.equal(res.status, 503);
    const body = await res.json();
    assert.equal(body.status, 503);
    assert.match(body.error, /departamentos/i);
  });

  it('responde 404 con el envoltorio de la casa en rutas desconocidas (con token)', async () => {
    const res = await fetch(`${gateway.url}/no-existe`, { headers: adminAuth() });
    assert.equal(res.status, 404);
    assert.deepEqual(await res.json(), { status: 404, error: 'Recurso no encontrado' });
  });

  it('enruta /perfiles/* al servicio de perfiles preservando ruta y query', async () => {
    const res = await fetch(`${gateway.url}/perfiles/E001?detalle=completo`, { headers: adminAuth() });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(perfiles.requests.at(-1).url, '/perfiles/E001?detalle=completo');
  });

  it('enruta /notificaciones/* al servicio de notificaciones preservando ruta y query', async () => {
    const res = await fetch(`${gateway.url}/notificaciones?empleado=E001`, { headers: adminAuth() });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(notificaciones.requests.at(-1).url, '/notificaciones?empleado=E001');
  });

  it('enruta /vacaciones/* al servicio de vacaciones preservando ruta y query', async () => {
    const res = await fetch(`${gateway.url}/vacaciones/E001?estado=pendiente`, { headers: adminAuth() });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(vacaciones.requests.at(-1).url, '/vacaciones/E001?estado=pendiente');
  });

  it('propaga el cuerpo y las cabeceras en un POST a vacaciones sin alterarlos', async () => {
    const payload = { empleadoId: 'E001', fechaInicio: '2025-01-10', dias: 5 };
    const res = await fetch(`${gateway.url}/vacaciones`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-test': 'vac', ...adminAuth() },
      body: JSON.stringify(payload),
    });
    assert.equal(res.status, 200);
    const seen = vacaciones.requests.at(-1);
    assert.equal(seen.method, 'POST');
    assert.equal(seen.url, '/vacaciones');
    assert.deepEqual(JSON.parse(seen.body), payload);
    assert.equal(seen.headers['x-test'], 'vac');
  });

  it('propaga el código de estado de vacaciones (400 de validación intacto)', async () => {
    const failing = await startEchoUpstream({
      status: 400,
      body: { status: 400, error: 'La fecha de fin debe ser posterior a la fecha de inicio' },
    });
    const gw = await listenEphemeral(
      createGateway({
        empleadosUrl: empleados.url,
        departamentosUrl: departamentos.url,
        perfilesUrl: perfiles.url,
        notificacionesUrl: notificaciones.url,
        vacacionesUrl: failing.url,
        authUrl: auth.url,
      }),
    );
    try {
      const res = await fetch(`${gw.url}/vacaciones`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', ...adminAuth() },
        body: JSON.stringify({ empleadoId: 'E001', dias: -1 }),
      });
      assert.equal(res.status, 400);
      assert.deepEqual(await res.json(), {
        status: 400,
        error: 'La fecha de fin debe ser posterior a la fecha de inicio',
      });
    } finally {
      gw.server.close();
      failing.server.close();
    }
  });

  it('responde 503 con JSON descriptivo si vacaciones no responde', async () => {
    const res = await fetch(`${gatewayVacacionesDown.url}/vacaciones/E001`, { headers: adminAuth() });
    assert.equal(res.status, 503);
    const body = await res.json();
    assert.equal(body.status, 503);
    assert.match(body.error, /vacaciones/i);
  });

  // -- Docs vía gateway (strip del prefijo, negocio intacto) --
  it('docs departamentos: /departamentos/api-docs/* llega como /api-docs/*', async () => {
    const res = await fetch(`${gateway.url}/departamentos/api-docs/swagger-ui.css`);
    assert.equal(res.status, 200);
    assert.equal(departamentos.requests.at(-1).url, '/api-docs/swagger-ui.css');
  });

  it('docs empleados: swagger-ui y v3 llegan en raíz', async () => {
    let res = await fetch(`${gateway.url}/empleados/swagger-ui/index.html`);
    assert.equal(res.status, 200);
    assert.equal(empleados.requests.at(-1).url, '/swagger-ui/index.html');
    res = await fetch(`${gateway.url}/empleados/v3/api-docs/swagger-config`);
    assert.equal(res.status, 200);
    assert.equal(empleados.requests.at(-1).url, '/v3/api-docs/swagger-config');
  });

  it('docs empleados: fallback absoluto para el JS de springdoc (/v3/api-docs sin prefijo)', async () => {
    const res = await fetch(`${gateway.url}/v3/api-docs/swagger-config`);
    assert.equal(res.status, 200);
    assert.equal(empleados.requests.at(-1).url, '/v3/api-docs/swagger-config');
  });

  it('docs notificaciones: /notificaciones/docs llega como /docs', async () => {
    const res = await fetch(`${gateway.url}/notificaciones/docs`);
    assert.equal(res.status, 200);
    assert.equal(notificaciones.requests.at(-1).url, '/docs');
  });

  it('docs notificaciones: openapi.json con query preservada', async () => {
    const res = await fetch(`${gateway.url}/notificaciones/openapi.json`);
    assert.equal(res.status, 200);
    assert.equal(notificaciones.requests.at(-1).url, '/openapi.json');
  });

  it('docs perfiles/vacaciones: openapi.yaml y docs con strip', async () => {
    let res = await fetch(`${gateway.url}/perfiles/openapi.yaml`);
    assert.equal(res.status, 200);
    assert.equal(perfiles.requests.at(-1).url, '/openapi.yaml');
    res = await fetch(`${gateway.url}/perfiles/docs`);
    assert.equal(res.status, 200);
    assert.equal(perfiles.requests.at(-1).url, '/docs');
    res = await fetch(`${gateway.url}/vacaciones/openapi.yaml`);
    assert.equal(res.status, 200);
    assert.equal(vacaciones.requests.at(-1).url, '/openapi.yaml');
    res = await fetch(`${gateway.url}/vacaciones/docs`);
    assert.equal(res.status, 200);
    assert.equal(vacaciones.requests.at(-1).url, '/docs');
  });

  // -- Seguridad JWT en el borde (Reto 5, paso 2) --
  it('responde 401 con el envoltorio de la casa en servicios sin token y no toca el upstream', async () => {
    const hits = empleados.requests.length;
    const res = await fetch(`${gateway.url}/empleados/E001`);
    assert.equal(res.status, 401);
    assert.deepEqual(await res.json(), {
      status: 401,
      error: 'Se requiere un token de acceso válido en el header Authorization',
    });
    assert.equal(empleados.requests.length, hits, 'el upstream no debe recibir la petición');
  });

  it('rechaza 401 bearer ausente, malformado, con firma ajena o vencido', async () => {
    const firmaAjena = jwt.sign({ sub: 'E001', role: 'ADMIN' }, 'otra-clave', {
      algorithm: 'HS256',
      expiresIn: '10m',
    });
    const vencido = jwt.sign({ sub: 'E001', role: 'ADMIN' }, TEST_JWT_SECRET, {
      algorithm: 'HS256',
      expiresIn: '-1h',
    });
    for (const authorization of [
      'Bearer',
      'Bearer no-es-un-jwt',
      'Token abc',
      `Bearer ${firmaAjena}`,
      `Bearer ${vencido}`,
    ]) {
      const res = await fetch(`${gateway.url}/departamentos/IT`, { headers: { authorization } });
      assert.equal(res.status, 401, `debe rechazar: ${authorization}`);
    }
  });

  it('rechaza un token de reset (type RESET_PASSWORD) como credencial de acceso', async () => {
    const reset = jwt.sign({ sub: 'E001', type: 'RESET_PASSWORD' }, TEST_JWT_SECRET, {
      algorithm: 'HS256',
      expiresIn: '10m',
    });
    const res = await fetch(`${gateway.url}/empleados`, {
      headers: { authorization: `Bearer ${reset}` },
    });
    assert.equal(res.status, 401);
  });

  it('requiere token también en rutas desconocidas (401, no filtra el 404)', async () => {
    const res = await fetch(`${gateway.url}/no-existe`);
    assert.equal(res.status, 401);
  });

  it('USER con token válido lee el negocio (GET 200 y ruta preservada)', async () => {
    const res = await fetch(`${gateway.url}/empleados/E001`, { headers: userE009() });
    assert.equal(res.status, 200);
    assert.equal(empleados.requests.at(-1).url, '/empleados/E001');
  });

  it('USER no puede borrar: 403 con envoltorio propio y sin tocar el upstream', async () => {
    const hits = departamentos.requests.length;
    const res = await fetch(`${gateway.url}/departamentos/IT`, {
      method: 'DELETE',
      headers: userE009(),
    });
    assert.equal(res.status, 403);
    assert.deepEqual(await res.json(), {
      status: 403,
      error: 'No tiene permisos para escribir en el servicio de departamentos',
    });
    assert.equal(departamentos.requests.length, hits, 'el upstream no debe recibir el DELETE');
  });

  it('USER no puede crear vacaciones: 403 sin tocar el upstream', async () => {
    const hits = vacaciones.requests.length;
    const res = await fetch(`${gateway.url}/vacaciones`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...userE009() },
      body: JSON.stringify({ empleadoId: 'E009', dias: 5 }),
    });
    assert.equal(res.status, 403);
    assert.equal(vacaciones.requests.length, hits);
  });

  it('USER puede actualizar su PROPIO perfil: 200 y llega al upstream', async () => {
    const payload = { telefono: '123456' };
    const res = await fetch(`${gateway.url}/perfiles/E009`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json', ...userE009() },
      body: JSON.stringify(payload),
    });
    assert.equal(res.status, 200);
    const seen = perfiles.requests.at(-1);
    assert.equal(seen.method, 'PUT');
    assert.equal(seen.url, '/perfiles/E009');
    assert.deepEqual(JSON.parse(seen.body), payload);
  });

  it('USER no puede modificar el perfil de OTRO empleado: 403 (no 401) sin upstream', async () => {
    const hits = perfiles.requests.length;
    const res = await fetch(`${gateway.url}/perfiles/E002`, {
      method: 'PUT',
      headers: userE009(),
    });
    assert.equal(res.status, 403);
    assert.equal(perfiles.requests.length, hits);
  });

  it('passthrough público de POST /auth/login sin token (el host ya no ve :8086)', async () => {
    const payload = { email: 'E009@ecosistema.com', password: 'Abcdef12' };
    const res = await fetch(`${gateway.url}/auth/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    assert.equal(res.status, 200);
    const seen = auth.requests.at(-1);
    assert.equal(seen.method, 'POST');
    assert.equal(seen.url, '/auth/login');
    assert.deepEqual(JSON.parse(seen.body), payload);
  });

  it('passthrough público de POST /auth/recover-password y /auth/bootstrap', async () => {
    let res = await fetch(`${gateway.url}/auth/recover-password`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email: 'E009@ecosistema.com' }),
    });
    assert.equal(res.status, 200);
    assert.equal(auth.requests.at(-1).url, '/auth/recover-password');
    res = await fetch(`${gateway.url}/auth/bootstrap`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ id: 'E001', password: 'Abcdef12' }),
    });
    assert.equal(res.status, 200);
    assert.equal(auth.requests.at(-1).url, '/auth/bootstrap');
  });

  it('POST /auth/change-password sin token responde 401 y no llega al upstream', async () => {
    const hits = auth.requests.length;
    const res = await fetch(`${gateway.url}/auth/change-password`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ passwordActual: 'Vieja123', passwordNueva: 'Nueva123' }),
    });
    assert.equal(res.status, 401);
    assert.equal(auth.requests.length, hits);
  });

  it('POST /auth/change-password con token USER reenvía la identidad verificada', async () => {
    const res = await fetch(`${gateway.url}/auth/change-password`, {
      method: 'POST',
      // x-user-id falsificado por el cliente: el gateway LO SOBREESCRIBE.
      headers: { 'content-type': 'application/json', 'x-user-id': 'E999', ...userE009() },
      body: JSON.stringify({ passwordActual: 'Vieja123', passwordNueva: 'Nueva123' }),
    });
    assert.equal(res.status, 200);
    const seen = auth.requests.at(-1);
    assert.equal(seen.url, '/auth/change-password');
    assert.equal(seen.headers['x-user-id'], 'E009');
    assert.equal(seen.headers['x-user-role'], 'USER');
  });
});
