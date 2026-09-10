import { describe, test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp } from '../src/app.js';
import { InMemoryDepartamentoStore } from '../src/store/InMemoryDepartamentoStore.js';

function makeApp() {
  const store = new InMemoryDepartamentoStore();
  const app = createApp({ store });
  return { app, store };
}

describe('POST /departamentos', () => {
  test('creates a departamento and returns 201 with the created object', async () => {
    const { app } = makeApp();
    const res = await request(app)
      .post('/departamentos')
      .send({ id: 'IT', nombre: 'Tecnología', descripcion: 'Área de TI' });
    assert.equal(res.status, 201);
    assert.deepEqual(res.body, { id: 'IT', nombre: 'Tecnología', descripcion: 'Área de TI' });
  });

  test('returns 400 envelope when the id is duplicated', async () => {
    const { app, store } = makeApp();
    await store.create({ id: 'IT', nombre: 'Tecnología', descripcion: 'Área de TI' });
    const res = await request(app)
      .post('/departamentos')
      .send({ id: 'IT', nombre: 'Otro', descripcion: 'x' });
    assert.equal(res.status, 400);
    assert.equal(res.body.status, 400);
    assert.match(res.body.error, /ya existe/);
  });

  test('returns 400 envelope when a required field is missing', async () => {
    const { app } = makeApp();
    const res = await request(app)
      .post('/departamentos')
      .send({ id: 'IT', nombre: 'Tecnología' }); // falta descripcion
    assert.equal(res.status, 400);
    assert.equal(res.body.status, 400);
    assert.match(res.body.error, /obligatorios/);
  });

  test('returns 400 envelope when id is missing too', async () => {
    const { app } = makeApp();
    const res = await request(app)
      .post('/departamentos')
      .send({ nombre: 'Tecnología', descripcion: 'Área de TI' }); // falta id
    assert.equal(res.status, 400);
    assert.equal(res.body.status, 400);
    assert.match(res.body.error, /obligatorios/);
  });

  test('error responses use the JSON envelope with Content-Type application/json', async () => {
    const { app } = makeApp();
    const res = await request(app)
      .post('/departamentos')
      .send({ id: 'IT' });
    assert.equal(res.status, 400);
    assert.match(res.headers['content-type'], /application\/json/);
    assert.deepEqual(Object.keys(res.body).sort(), ['error', 'status']);
  });
});

describe('GET /departamentos/:id', () => {
  test('returns 200 with the departamento when it exists', async () => {
    const { app, store } = makeApp();
    await store.create({ id: 'IT', nombre: 'Tecnología', descripcion: 'Área de TI' });
    const res = await request(app).get('/departamentos/IT');
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, { id: 'IT', nombre: 'Tecnología', descripcion: 'Área de TI' });
  });

  test('returns 404 envelope when the id is unknown', async () => {
    const { app } = makeApp();
    const res = await request(app).get('/departamentos/NOPE');
    assert.equal(res.status, 404);
    assert.deepEqual(res.body, { status: 404, error: 'El departamento con id NOPE no existe' });
  });
});

describe('GET /departamentos', () => {
  test('returns an empty array when there are no departamentos', async () => {
    const { app } = makeApp();
    const res = await request(app).get('/departamentos');
    assert.equal(res.status, 200);
    assert.deepEqual(res.body, []);
  });

  test('returns the full list of departamentos', async () => {
    const { app, store } = makeApp();
    await store.create({ id: 'IT', nombre: 'Tecnología', descripcion: 'Área de TI' });
    await store.create({ id: 'RH', nombre: 'Recursos Humanos', descripcion: 'Área de RRHH' });
    const res = await request(app).get('/departamentos');
    assert.equal(res.status, 200);
    assert.equal(res.body.length, 2);
  });
});

describe('Swagger UI', () => {
  test('serves the documentation at /api-docs', async () => {
    const { app } = makeApp();
    const res = await request(app).get('/api-docs/');
    assert.equal(res.status, 200);
  });
});
