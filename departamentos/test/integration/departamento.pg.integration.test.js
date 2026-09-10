import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createPool } from '../../src/config/db.js';
import { PgDepartamentoStore } from '../../src/store/PgDepartamentoStore.js';
import { createApp } from '../../src/app.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INIT_SQL = fs.readFileSync(path.join(__dirname, '..', '..', 'init.sql'), 'utf8');

const TEST_IDS = ['PG-IT', 'PG-RRHH'];

function loadConfig() {
  return {
    host: process.env.DB_HOST || 'localhost',
    port: Number(process.env.DB_PORT || 5432),
    database: process.env.DB_NAME || 'departamentos',
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD || 'postgres',
  };
}

describe('Integration with real PostgreSQL', { concurrency: false, skip: false }, (t) => {
  let pool;
  let app;
  let store;

  test('exercises the full flow against PostgreSQL', async (t) => {
    pool = createPool();
    store = new PgDepartamentoStore(pool);
    app = createApp({ store });

    // Probe connectivity; skip the suite when PostgreSQL is unreachable.
    try {
      await pool.query('SELECT 1');
    } catch (err) {
      t.skip(`PostgreSQL no disponible (${loadConfig().host}:${loadConfig().port}): ${err.message}`);
      await pool.end();
      return;
    }

    // Ensure the schema exists (idempotent, non-destructive).
    await pool.query(INIT_SQL);

    try {
      // POST valid -> 201
      const created = await request(app)
        .post('/departamentos')
        .send({ id: TEST_IDS[0], nombre: 'Tecnología PG', descripcion: 'Área de TI (integración)' });
      assert.equal(created.status, 201);
      assert.equal(created.body.id, TEST_IDS[0]);

      // POST duplicate -> 400 envelope
      const duplicate = await request(app)
        .post('/departamentos')
        .send({ id: TEST_IDS[0], nombre: 'Otro', descripcion: 'x' });
      assert.equal(duplicate.status, 400);
      assert.equal(duplicate.body.status, 400);
      assert.match(duplicate.body.error, /ya existe/);

      // GET existing -> 200
      const found = await request(app).get(`/departamentos/${TEST_IDS[0]}`);
      assert.equal(found.status, 200);
      assert.equal(found.body.id, TEST_IDS[0]);

      // GET unknown -> 404 envelope
      const missing = await request(app).get('/departamentos/PG-NO-EXISTE');
      assert.equal(missing.status, 404);
      assert.deepEqual(missing.body, {
        status: 404,
        error: 'El departamento con id PG-NO-EXISTE no existe',
      });

      // GET list -> 200 array containing the created row
      const listBefore = (await request(app).get('/departamentos')).body;
      assert.ok(Array.isArray(listBefore));
      assert.equal(listBefore.status === undefined, true);
      assert.ok(listBefore.some((d) => d.id === TEST_IDS[0]));
    } finally {
      // Cleanup: remove only the rows created by this test.
      await pool.query('DELETE FROM departamentos WHERE id = ANY($1)', [TEST_IDS]);
      await pool.end();
    }
  });
});