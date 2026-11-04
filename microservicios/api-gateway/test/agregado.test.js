import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import jwt from 'jsonwebtoken';
import { createGateway } from '../src/app.js';

/**
 * Proyecto Final (T5, opcional con puntaje): endpoint agregado del Gateway.
 * GET /empleados/:id/completo combina empleado + perfil en una sola respuesta
 * y degrada con gracia si perfiles no contesta (200 con perfil null).
 *
 * Sin Docker: upstreams falsos con cuerpos fijos (empleado vs perfil).
 */

const TEST_JWT_SECRET = 'secreto-compartido-api-gateway';

function bearer({ sub = 'E001', role = 'ADMIN', expiresIn = '10m' } = {}) {
  return jwt.sign({ sub, role }, TEST_JWT_SECRET, { algorithm: 'HS256', expiresIn });
}
const adminAuth = () => ({ authorization: `Bearer ${bearer()}` });

const EMPLEADO = { id: 'E001', nombre: 'Ada', email: 'ada@empresa.com', estado: 'ACTIVO' };
const PERFIL = { empleadoId: 'E001', telefono: '3001234567', ciudad: 'Armenia' };

function startCannedUpstream(body, { status = 200 } = {}) {
  const requests = [];
  const server = http.createServer((req, res) => {
    requests.push({ method: req.method, url: req.url });
    res.writeHead(status, { 'content-type': 'application/json' });
    res.end(JSON.stringify(body));
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, requests, url: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

function listenEphemeral(app) {
  return new Promise((resolve) => {
    const server = app.listen(0, '127.0.0.1', () => {
      resolve({ server, url: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

async function get(url, headers = {}) {
  const res = await fetch(url, { headers });
  return { status: res.status, body: await res.json() };
}

describe('GET /empleados/:id/completo', () => {
  let empleados;
  let perfiles;
  let empleados404;
  let gateway;
  let gatewayPerfilCaido;
  let gatewayEmpleado404;
  let secretOriginal;

  before(async () => {
    secretOriginal = process.env.JWT_SECRET;
    process.env.JWT_SECRET = TEST_JWT_SECRET;
    empleados = await startCannedUpstream(EMPLEADO);
    perfiles = await startCannedUpstream(PERFIL);
    empleados404 = await startCannedUpstream({ status: 404, error: 'no existe' }, { status: 404 });
    const resto = { departamentosUrl: empleados.url, notificacionesUrl: empleados.url, vacacionesUrl: empleados.url, authUrl: empleados.url };
    gateway = await listenEphemeral(createGateway({ empleadosUrl: empleados.url, perfilesUrl: perfiles.url, ...resto }));
    gatewayPerfilCaido = await listenEphemeral(
      createGateway({ empleadosUrl: empleados.url, perfilesUrl: 'http://127.0.0.1:1', ...resto }),
    );
    gatewayEmpleado404 = await listenEphemeral(
      createGateway({ empleadosUrl: empleados404.url, perfilesUrl: perfiles.url, ...resto }),
    );
  });

  after(() => {
    for (const s of [empleados, perfiles, empleados404, gateway, gatewayPerfilCaido, gatewayEmpleado404]) {
      s.server.close();
    }
    if (secretOriginal === undefined) delete process.env.JWT_SECRET;
    else process.env.JWT_SECRET = secretOriginal;
  });

  it('401 sin token', async () => {
    const { status, body } = await get(`${gateway.url}/empleados/E001/completo`);
    assert.equal(status, 401);
    assert.equal(body.status, 401);
  });

  it('200 compone empleado + perfil y pide las rutas upstream exactas', async () => {
    const { status, body } = await get(`${gateway.url}/empleados/E001/completo`, adminAuth());
    assert.equal(status, 200);
    assert.deepEqual(body.empleado, EMPLEADO);
    assert.deepEqual(body.perfil, PERFIL);
    assert.equal(body.degradado, false);
    assert.ok(empleados.requests.some((r) => r.url === '/empleados/E001'), 'upstream empleados');
    assert.ok(perfiles.requests.some((r) => r.url === '/perfiles/E001'), 'upstream perfiles');
  });

  it('200 degradado con perfil null si perfiles no contesta', async () => {
    const { status, body } = await get(`${gatewayPerfilCaido.url}/empleados/E001/completo`, adminAuth());
    assert.equal(status, 200);
    assert.deepEqual(body.empleado, EMPLEADO);
    assert.equal(body.perfil, null);
    assert.equal(body.degradado, true);
  });

  it('404 si el empleado no existe', async () => {
    const { status } = await get(`${gatewayEmpleado404.url}/empleados/E999/completo`, adminAuth());
    assert.equal(status, 404);
  });
});
