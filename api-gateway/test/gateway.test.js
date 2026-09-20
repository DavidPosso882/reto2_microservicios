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
  let gateway;
  let gatewayDownstream;

  before(async () => {
    empleados = await startEchoUpstream();
    departamentos = await startEchoUpstream();
    gateway = await listenEphemeral(
      createGateway({ empleadosUrl: empleados.url, departamentosUrl: departamentos.url }),
    );
    // Gateway whose departamentos destination is unreachable (closed port 1).
    gatewayDownstream = await listenEphemeral(
      createGateway({ empleadosUrl: empleados.url, departamentosUrl: 'http://127.0.0.1:1' }),
    );
  });

  after(() => {
    empleados.server.close();
    departamentos.server.close();
    gateway.server.close();
    gatewayDownstream.server.close();
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
      createGateway({ empleadosUrl: empleados.url, departamentosUrl: failing.url }),
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
});
