import { describe, test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp } from '../src/app.js';
import { InMemoryUsuarioStore } from '../src/store/UsuarioStore.js';

process.env.JWT_SECRET = 'secreto-de-prueba-reto5';

function contenedores() {
  const store = new InMemoryUsuarioStore();
  const publicados = [];
  const eventPublisher = async (type, data) => {
    publicados.push({ type, data });
  };
  const app = createApp({ store, eventPublisher });
  return { app, store, publicados };
}

async function sembrarAdminYUsuario({ app, store }) {
  const resp = await request(app)
    .post('/auth/bootstrap')
    .send({ email: 'admin@empresa.com', password: 'AdminClave1' });
  if (resp.status !== 201 && resp.status !== 400) {
    throw new Error(`bootstrap falló con ${resp.status}: ${JSON.stringify(resp.body)}`);
  }
  await store.crear({
    id: 'E001',
    email: 'e001@empresa.com',
    passwordHash: null,
    role: 'USER',
    estado: 'ACTIVA',
  });
}

describe('POST /auth/bootstrap', () => {
  beforeEach(() => {});

  test('crea el ADMIN semilla solo con la tabla de usuarios vacía (201)', async () => {
    const { app, store } = contenedores();
    const res = await request(app)
      .post('/auth/bootstrap')
      .send({ email: 'admin@empresa.com', password: 'AdminClave1' });
    assert.equal(res.status, 201);
    assert.equal(res.body.id, 'ADMIN');
    assert.equal(res.body.role, 'ADMIN');
    assert.equal(res.body.estado, 'ACTIVA');
    assert.ok(await store.buscarPorId('ADMIN'));
  });

  test('nunca devuelve el password en la respuesta', async () => {
    const { app } = contenedores();
    const res = await request(app)
      .post('/auth/bootstrap')
      .send({ email: 'admin@empresa.com', password: 'AdminClave1' });
    assert.equal(res.status, 201);
    assert.equal(res.body.email, 'admin@empresa.com');
    assert.equal(res.body.password, undefined);
    assert.equal(res.body.passwordHash, undefined);
    // Ningún campo del cuerpo puede contener la palabra "password".
    assert.match(JSON.stringify(res.body), /^(?!.*(password|Password)).*$/);
  });

  test('rechaza un segundo bootstrap con 400 (ya existe el ADMIN)', async () => {
    const { app } = contenedores();
    await request(app)
      .post('/auth/bootstrap')
      .send({ email: 'a@empresa.com', password: 'AdminClave1' });
    const res = await request(app)
      .post('/auth/bootstrap')
      .send({ email: 'otro@empresa.com', password: 'OtraClave1' });
    assert.equal(res.status, 400);
    assert.match(res.body.error, /solo está disponible/);
  });

  test('rechaza password que no cumple la política', async () => {
    const { app } = contenedores();
    const res = await request(app)
      .post('/auth/bootstrap')
      .send({ email: 'admin@empresa.com', password: 'corta' });
    assert.equal(res.status, 400);
    assert.match(res.body.error, /al menos 8/);
  });
});

describe('POST /auth/login', () => {
  test('retorna accessToken con payload {sub, role} para credenciales válidas', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    // Set a real BCrypt hash via the same helper the service uses.
    const { hashPassword } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ClaveNueva1'));
    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'ClaveNueva1' });
    assert.equal(res.status, 200);
    assert.ok(res.body.accessToken);
    assert.equal(res.body.tokenType, 'Bearer');
    assert.equal(res.body.usuario.id, 'E001');
    assert.equal(res.body.usuario.role, 'USER');
    // Never leaks hashes/tokens other than the access token.
    assert.equal(res.body.usuario.passwordHash, undefined);
  });

  test('rechaza 401 con contraseña incorrecta', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { hashPassword } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ClaveNueva1'));
    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'OtraClave9' });
    assert.equal(res.status, 401);
    assert.deepEqual(Object.keys(res.body).sort(), ['error', 'status']);
  });

  test('rechaza 401 con cuenta SUSPENDIDA_TEMPORAL (vacaciones)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { hashPassword } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ClaveNueva1'));
    await store.actualizarEstado('E001', 'SUSPENDIDA_TEMPORAL');
    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'ClaveNueva1' });
    assert.equal(res.status, 401);
    assert.match(res.body.error, /no activa/);
  });

  test('rechaza 401 con cuenta DESACTIVADA_PERMANENTE (retiro)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { hashPassword } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ClaveNueva1'));
    await store.actualizarEstado('E001', 'DESACTIVADA_PERMANENTE');
    const res = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'ClaveNueva1' });
    assert.equal(res.status, 401);
  });
});

describe('POST /auth/recover-password', () => {
  test('publica usuario.recuperacion con reset token cuando el email existe', async () => {
    const { app, store, publicados } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const res = await request(app)
      .post('/auth/recover-password')
      .send({ email: 'e001@empresa.com' });
    assert.equal(res.status, 200);
    assert.equal(res.body.enviado, true);
    assert.equal(publicados.length, 1);
    assert.equal(publicados[0].type, 'usuario.recuperacion');
    assert.equal(publicados[0].data.empleadoId, 'E001');
    assert.ok(publicados[0].data.resetToken);
    // The HTTP response never reveals the reset token.
    assert.equal(JSON.stringify(res.body).includes(publicados[0].data.resetToken), false);
  });

  test('responde 200 uniforme cuando el email no existe (sin evento)', async () => {
    const { app, publicados } = contenedores();
    const res = await request(app)
      .post('/auth/recover-password')
      .send({ email: 'fantasma@empresa.com' });
    assert.equal(res.status, 200);
    assert.equal(publicados.length, 0);
  });
});

describe('POST /auth/reset-password', () => {
  test('establece contraseña con reset token de empleado.creado y activa la cuenta', async () => {
    const { app, store, publicados } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    // Estado real de alta: la cuenta nace suspendida hasta el reset
    // (empleado.creado); el reset la activa y publica cuenta.activada.
    await store.actualizarEstado('E001', 'SUSPENDIDA_TEMPORAL');
    const { issueResetToken } = await import('../src/tokens.js');
    const cuenta = await store.buscarPorId('E001');
    const resetToken = issueResetToken(cuenta);
    const res = await request(app)
      .post('/auth/reset-password')
      .send({ token: resetToken, nuevaPassword: 'ClaveNueva1' });
    assert.equal(res.status, 200);
    assert.equal(res.body.usuario.estado, 'ACTIVA');
    // cuenta.activada published on first activation.
    assert.ok(publicados.some((e) => e.type === 'cuenta.activada'));
    // Now login works with the established password.
    const login = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'ClaveNueva1' });
    assert.equal(login.status, 200);
  });

  test('rechaza token de acceso usado como reset token (401)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { issueAccessToken } = await import('../src/tokens.js');
    const admin = await store.buscarPorId('ADMIN');
    const accessToken = issueAccessToken(admin);
    const res = await request(app)
      .post('/auth/reset-password')
      .send({ token: accessToken, nuevaPassword: 'ClaveNueva1' });
    assert.equal(res.status, 401);
  });

  test('rechaza reset token firmado con otro secreto (401)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    process.env.JWT_SECRET = 'otro-secreto';
    const { issueResetToken } = await import('../src/tokens.js');
    const cuenta = await store.buscarPorId('E001');
    const resetToken = issueResetToken(cuenta);
    process.env.JWT_SECRET = 'secreto-de-prueba-reto5';
    const res = await request(app)
      .post('/auth/reset-password')
      .send({ token: resetToken, nuevaPassword: 'ClaveNueva1' });
    assert.equal(res.status, 401);
  });

  test('rechaza nueva contraseña que no cumple la política (400)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { issueResetToken } = await import('../src/tokens.js');
    const cuenta = await store.buscarPorId('E001');
    const resetToken = issueResetToken(cuenta);
    const res = await request(app)
      .post('/auth/reset-password')
      .send({ token: resetToken, nuevaPassword: 'debil' });
    assert.equal(res.status, 400);
    assert.match(res.body.error, /contraseña/i);
  });

  test('rechaza reset cuando la cuenta está desactivada permanentemente', async () => {
    const { app, store, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({ id: 'E105', email: 'e105@empresa.com' });
    // Token emitido en el alta, ANTES del retiro: con la cuenta ya en baja
    // permanente el reset no debe reactivarla ni publicar cuenta.activada.
    const { issueResetToken } = await import('../src/tokens.js');
    const cuentaAlRetiro = await store.buscarPorId('E105');
    const resetTokenPreRetiro = issueResetToken(cuentaAlRetiro);
    await service.aplicarEmpleadoRetirado({ id: 'E105' });
    publicados.length = 0;
    const res = await request(app)
      .post('/auth/reset-password')
      .send({ token: resetTokenPreRetiro, nuevaPassword: 'ClaveNueva1' });
    // Uniform 401: no revela si la cuenta está desactivada (anti-enumeración).
    assert.equal(res.status, 401);
    assert.match(res.body.error, /token/i);
    const cuenta = await store.buscarPorId('E105');
    assert.equal(cuenta.estado, 'DESACTIVADA_PERMANENTE');
    assert.equal(cuenta.passwordHash, null);
    assert.ok(publicados.every((e) => e.type !== 'cuenta.activada'));
  });
});

describe('POST /auth/change-password', () => {
  test('cambia la contraseña con identidad de gateway (X-User-Id) y Login cambia', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { hashPassword } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ActualClave1'));
    const res = await request(app)
      .post('/auth/change-password')
      .set('X-User-Id', 'E001')
      .set('X-User-Role', 'USER')
      .send({ passwordActual: 'ActualClave1', passwordNueva: 'NuevaClave2' });
    assert.equal(res.status, 200);
    const viejo = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'ActualClave1' });
    assert.equal(viejo.status, 401);
    const nuevo = await request(app)
      .post('/auth/login')
      .send({ email: 'e001@empresa.com', password: 'NuevaClave2' });
    assert.equal(nuevo.status, 200);
  });

  test('funciona con JWT de acceso directo (sin headers de gateway)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { hashPassword, issueAccessToken } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ActualClave1'));
    const cuenta = await store.buscarPorId('E001');
    const token = issueAccessToken(cuenta);
    const res = await request(app)
      .post('/auth/change-password')
      .set('Authorization', `Bearer ${token}`)
      .send({ passwordActual: 'ActualClave1', passwordNueva: 'NuevaClave2' });
    assert.equal(res.status, 200);
  });

  test('rechaza 401 sin identidad ni token', async () => {
    const { app } = contenedores();
    const res = await request(app)
      .post('/auth/change-password')
      .send({ passwordActual: 'x', passwordNueva: 'y' });
    assert.equal(res.status, 401);
  });

  test('rechaza reset token usado como acceso (401)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { issueResetToken } = await import('../src/tokens.js');
    const cuenta = await store.buscarPorId('E001');
    const resetToken = issueResetToken(cuenta);
    const res = await request(app)
      .post('/auth/change-password')
      .set('Authorization', `Bearer ${resetToken}`)
      .send({ passwordActual: 'ActualClave1', passwordNueva: 'NuevaClave2' });
    assert.equal(res.status, 401);
  });

  test('rechaza contraseña actual incorrecta (400)', async () => {
    const { app, store } = contenedores();
    await sembrarAdminYUsuario({ app, store });
    const { hashPassword } = await import('../src/tokens.js');
    await store.actualizarPasswordHash('E001', await hashPassword('ActualClave1'));
    const res = await request(app)
      .post('/auth/change-password')
      .set('X-User-Id', 'E001')
      .set('X-User-Role', 'USER')
      .send({ passwordActual: 'Incorrecta1', passwordNueva: 'NuevaClave2' });
    assert.equal(res.status, 400);
  });
});

describe('Ciclo de vida por eventos (servicio de dominio)', () => {
  test('empleado.creado crea cuenta USER sin password y publica usuario.creado con reset token', async () => {
    const { app, store, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({
      id: 'E100',
      email: 'E100@empresa.com',
      nombre: 'Nueva',
      apellido: 'Persona',
    });
    const cuenta = await store.buscarPorId('E100');
    assert.equal(cuenta.role, 'USER');
    assert.equal(cuenta.passwordHash, null);
    const evento = publicados.find((e) => e.type === 'usuario.creado');
    assert.ok(evento);
    assert.ok(evento.data.resetToken);
    assert.equal(evento.data.email, 'e100@empresa.com');
  });

  test('empleado.retirado desactiva permanente y publica cuenta.desactivada RETIRO', async () => {
    const { app, store, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({ id: 'E101', email: 'e101@empresa.com' });
    publicados.length = 0;
    await service.aplicarEmpleadoRetirado({ id: 'E101' });
    const cuenta = await store.buscarPorId('E101');
    assert.equal(cuenta.estado, 'DESACTIVADA_PERMANENTE');
    const evento = publicados.find((e) => e.type === 'cuenta.desactivada');
    assert.ok(evento);
    assert.equal(evento.data.motivo, 'RETIRO');
    assert.equal(evento.data.permanente, true);
  });

  test('vacaciones.iniciadas suspende temporal y publica cuenta.desactivada VACACIONES', async () => {
    const { app, store, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({ id: 'E102', email: 'e102@empresa.com' });
    publicados.length = 0;
    await service.aplicarVacacionesIniciadas({ empleadoId: 'E102' });
    const cuenta = await store.buscarPorId('E102');
    assert.equal(cuenta.estado, 'SUSPENDIDA_TEMPORAL');
    const evento = publicados.find((e) => e.type === 'cuenta.desactivada');
    assert.ok(evento);
    assert.equal(evento.data.motivo, 'VACACIONES');
    assert.equal(evento.data.permanente, false);
  });

  test('vacaciones.finalizadas reactiva cuenta suspendida y publica cuenta.activada FIN_VACACIONES', async () => {
    const { app, store, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({ id: 'E103', email: 'e103@empresa.com' });
    await service.aplicarVacacionesIniciadas({ empleadoId: 'E103' });
    publicados.length = 0;
    await service.aplicarVacacionesFinalizadas({ empleadoId: 'E103' });
    const cuenta = await store.buscarPorId('E103');
    assert.equal(cuenta.estado, 'ACTIVA');
    const evento = publicados.find((e) => e.type === 'cuenta.activada');
    assert.ok(evento);
    assert.equal(evento.data.motivo, 'FIN_VACACIONES');
  });

  test('caso borde: retiro durante vacaciones NO se reactiva con vacaciones.finalizadas', async () => {
    const { app, store, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({ id: 'E104', email: 'e104@empresa.com' });
    await service.aplicarVacacionesIniciadas({ empleadoId: 'E104' });
    await service.aplicarEmpleadoRetirado({ id: 'E104' });
    let cuenta = await store.buscarPorId('E104');
    assert.equal(cuenta.estado, 'DESACTIVADA_PERMANENTE');
    publicados.length = 0;
    await service.aplicarVacacionesFinalizadas({ empleadoId: 'E104' });
    cuenta = await store.buscarPorId('E104');
    assert.equal(cuenta.estado, 'DESACTIVADA_PERMANENTE');
    assert.equal(publicados.length, 0);
  });

  test('aplicarEmpleadoCreado es idempotente (no repite usuario.creado)', async () => {
    const { app, publicados } = contenedores();
    const service = app.locals.authService;
    await service.aplicarEmpleadoCreado({ id: 'E105', email: 'e105@empresa.com' });
    publicados.length = 0;
    await service.aplicarEmpleadoCreado({ id: 'E105', email: 'e105@empresa.com' });
    assert.equal(publicados.length, 0);
  });
});

describe('Responses y documentación', () => {
  test('404 en rutas desconocidas usa el envoltorio', async () => {
    const { app } = contenedores();
    const res = await request(app).get('/no-existe');
    assert.equal(res.status, 404);
    assert.deepEqual(Object.keys(res.body).sort(), ['error', 'status']);
  });

  test('health responde 200 con service auth-service', async () => {
    const { app } = contenedores();
    const res = await request(app).get('/health');
    assert.equal(res.status, 200);
    assert.equal(res.body.service, 'auth-service');
  });

  test('openapi.yaml expone BearerAuth y los 5 endpoints /auth', async () => {
    const { app } = contenedores();
    const res = await request(app).get('/openapi.yaml');
    assert.equal(res.status, 200);
    const texto = res.text;
    assert.match(texto, /BearerAuth/);
    for (const ruta of ['/auth/login', '/auth/recover-password', '/auth/reset-password', '/auth/change-password', '/auth/bootstrap']) {
      assert.ok(texto.includes(ruta), `openapi debe incluir ${ruta}`);
    }
  });

  test('Swagger UI se sirve en /docs', async () => {
    const { app } = contenedores();
    const res = await request(app).get('/docs/').redirects(1);
    assert.equal(res.status, 200);
    assert.match(res.text, /swagger|Swagger|openapi/i);
  });
});
