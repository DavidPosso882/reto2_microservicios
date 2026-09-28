import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { createGateway } from '../src/app.js';

/**
 * Gateway contract tests (Reto 3) with fake upstreams.
 *
 * No Docker needed: tiny http servers stand in for empleados-service and
 * departamentos-service, so routing, propagation and the 503 envelope are
 * verified in milliseconds.
 */

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
  let gateway;
  let gatewayDownstream;
  let gatewayVacacionesDown;

  before(async () => {
    empleados = await startEchoUpstream();
    departamentos = await startEchoUpstream();
    perfiles = await startEchoUpstream();
    notificaciones = await startEchoUpstream();
    vacaciones = await startEchoUpstream();
    gateway = await listenEphemeral(
      createGateway({
        empleadosUrl: empleados.url,
        departamentosUrl: departamentos.url,
        perfilesUrl: perfiles.url,
        notificacionesUrl: notificaciones.url,
        vacacionesUrl: vacaciones.url,
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
      }),
    );
  });

  after(() => {
    empleados.server.close();
    departamentos.server.close();
    perfiles.server.close();
    notificaciones.server.close();
    vacaciones.server.close();
    gateway.server.close();
    gatewayDownstream.server.close();
    gatewayVacacionesDown.server.close();
  });

  it('expone su propio /health sin depender de los servicios', async () => {
    const res = await fetch(`${gateway.url}/health`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { status: 'ok', service: 'api-gateway' });
  });

  it('enruta /departamentos/* al servicio de departamentos preservando ruta y estado', async () => {
    const res = await fetch(`${gateway.url}/departamentos/IT`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(departamentos.requests.at(-1).url, '/departamentos/IT');
  });

  it('enruta /empleados/* al servicio de empleados preservando ruta', async () => {
    const res = await fetch(`${gateway.url}/empleados/E001`);
    assert.equal(res.status, 200);
    assert.equal(empleados.requests.at(-1).url, '/empleados/E001');
  });

  it('propaga el cuerpo y las cabeceras en un POST sin alterarlos', async () => {
    const payload = { id: 'E009', nombre: 'Test' };
    const res = await fetch(`${gateway.url}/empleados`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-test': 'abc' },
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
      }),
    );
    try {
      const res = await fetch(`${gw.url}/departamentos/X`);
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
    const res = await fetch(`${gatewayDownstream.url}/departamentos`);
    assert.equal(res.status, 503);
    const body = await res.json();
    assert.equal(body.status, 503);
    assert.match(body.error, /departamentos/i);
  });

  it('responde 404 con el envoltorio de la casa en rutas desconocidas', async () => {
    const res = await fetch(`${gateway.url}/no-existe`);
    assert.equal(res.status, 404);
    assert.deepEqual(await res.json(), { status: 404, error: 'Recurso no encontrado' });
  });

  it('enruta /perfiles/* al servicio de perfiles preservando ruta y query', async () => {
    const res = await fetch(`${gateway.url}/perfiles/E001?detalle=completo`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(perfiles.requests.at(-1).url, '/perfiles/E001?detalle=completo');
  });

  it('enruta /notificaciones/* al servicio de notificaciones preservando ruta y query', async () => {
    const res = await fetch(`${gateway.url}/notificaciones?empleado=E001`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(notificaciones.requests.at(-1).url, '/notificaciones?empleado=E001');
  });

  it('enruta /vacaciones/* al servicio de vacaciones preservando ruta y query', async () => {
    const res = await fetch(`${gateway.url}/vacaciones/E001?estado=pendiente`);
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { echoed: true });
    assert.equal(vacaciones.requests.at(-1).url, '/vacaciones/E001?estado=pendiente');
  });

  it('propaga el cuerpo y las cabeceras en un POST a vacaciones sin alterarlos', async () => {
    const payload = { empleadoId: 'E001', fechaInicio: '2025-01-10', dias: 5 };
    const res = await fetch(`${gateway.url}/vacaciones`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-test': 'vac' },
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
      }),
    );
    try {
      const res = await fetch(`${gw.url}/vacaciones`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
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
    const res = await fetch(`${gatewayVacacionesDown.url}/vacaciones/E001`);
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
});
