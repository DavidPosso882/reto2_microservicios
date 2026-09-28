import { AppError, ValidationError } from '../errors.js';

const ESTADOS_VALIDOS = ['ACTIVA', 'SUSPENDIDA_TEMPORAL', 'DESACTIVADA_PERMANENTE'];
const ROLES_VALIDOS = ['ADMIN', 'USER'];

/**
 * PostgreSQL-backed account store.
 *
 * Parameterized queries only. Idempotent DDL (EnsureSchema) runs at boot so a
 * mounted init.sql is not required for the schema to exist.
 */
export class PgUsuarioStore {
  constructor(pool) {
    this.pool = pool;
    this.ready = this.aplicarSchema();
  }

  async aplicarSchema() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS usuarios (
        id TEXT PRIMARY KEY,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        role TEXT NOT NULL,
        estado TEXT NOT NULL,
        fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now(),
        fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (email);
      CREATE TABLE IF NOT EXISTS eventos_procesados (
        id TEXT PRIMARY KEY,
        procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
      );
    `);
  }

  async esperarListo() {
    await this.ready;
  }

  async contarUsuarios() {
    await this.esperarListo();
    const { rows } = await this.pool.query('SELECT COUNT(*)::int AS n FROM usuarios');
    return rows[0].n;
  }

  async crear(usuario) {
    await this.esperarListo();
    await this.pool.query(
      `INSERT INTO usuarios (id, email, password_hash, role, estado)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (id) DO NOTHING`,
      [usuario.id, usuario.email, usuario.passwordHash, usuario.role, usuario.estado]
    );
  }

  async actualizarEstado(id, estado) {
    await this.esperarListo();
    if (!ESTADOS_VALIDOS.includes(estado)) {
      throw new ValidationError(`Estado inválido: ${estado}`);
    }
    await this.pool.query(
      `UPDATE usuarios SET estado = $2, fecha_actualizacion = now() WHERE id = $1`,
      [id, estado]
    );
  }

  async actualizarPasswordHash(id, passwordHash) {
    await this.esperarListo();
    await this.pool.query(
      `UPDATE usuarios SET password_hash = $2, fecha_actualizacion = now() WHERE id = $1`,
      [id, passwordHash]
    );
  }

  async buscarPorId(id) {
    await this.esperarListo();
    const { rows } = await this.pool.query(
      'SELECT id, email, password_hash, role, estado FROM usuarios WHERE id = $1',
      [id]
    );
    return rows[0] ? mapear(rows[0]) : null;
  }

  async buscarPorEmail(email) {
    await this.esperarListo();
    const { rows } = await this.pool.query(
      'SELECT id, email, password_hash, role, estado FROM usuarios WHERE email = $1',
      [email]
    );
    return rows[0] ? mapear(rows[0]) : null;
  }

  async procesados(id) {
    await this.esperarListo();
    const { rows } = await this.pool.query(
      'SELECT 1 FROM eventos_procesados WHERE id = $1',
      [id]
    );
    return rows.length > 0;
  }

  async marcarProcesado(id) {
    await this.esperarListo();
    await this.pool.query(
      'INSERT INTO eventos_procesados (id) VALUES ($1) ON CONFLICT (id) DO NOTHING',
      [id]
    );
  }
}

function mapear(row) {
  return {
    id: row.id,
    email: row.email,
    passwordHash: row.password_hash,
    role: row.role,
    estado: row.estado,
  };
}

/**
 * In-memory account store for tests (identical contract, no database).
 */
export class InMemoryUsuarioStore {
  constructor() {
    this.usuarios = new Map();
    this.deduplicacion = new Map();
  }

  async contarUsuarios() {
    return this.usuarios.size;
  }

  async crear(usuario) {
    if (!this.usuarios.has(usuario.id)) {
      this.usuarios.set(usuario.id, { ...usuario });
    }
  }

  async actualizarEstado(id, estado) {
    if (!ESTADOS_VALIDOS.includes(estado)) {
      throw new ValidationError(`Estado inválido: ${estado}`);
    }
    const u = this.usuarios.get(id);
    if (u) {
      u.estado = estado;
    }
  }

  async actualizarPasswordHash(id, passwordHash) {
    const u = this.usuarios.get(id);
    if (u) {
      u.passwordHash = passwordHash;
    }
  }

  async buscarPorId(id) {
    return this.usuarios.get(id) || null;
  }

  async buscarPorEmail(email) {
    for (const u of this.usuarios.values()) {
      if (u.email === email) return u;
    }
    return null;
  }

  async procesados(id) {
    return this.deduplicacion.has(id);
  }

  async marcarProcesado(id) {
    if (!this.deduplicacion.has(id)) {
      this.deduplicacion.set(id, new Date().toISOString());
    }
  }
}
