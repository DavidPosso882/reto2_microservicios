import { DuplicateError } from '../errors.js';

/**
 * PostgreSQL-backed implementation of the departamento store.
 *
 * Uses parameterized queries to prevent SQL injection. A unique-violation
 * (Postgres error code 23505) is translated into a `DuplicateError` (400).
 */
export class PgDepartamentoStore {
  constructor(pool) {
    this.pool = pool;
  }

  async create(departamento) {
    try {
      const { rows } = await this.pool.query(
        'INSERT INTO departamentos (id, nombre, descripcion) VALUES ($1, $2, $3) RETURNING id, nombre, descripcion',
        [departamento.id, departamento.nombre, departamento.descripcion]
      );
      return rows[0];
    } catch (err) {
      if (err && err.code === '23505') {
        throw new DuplicateError(`El departamento con id ${departamento.id} ya existe`);
      }
      throw err;
    }
  }

  async findById(id) {
    const { rows } = await this.pool.query(
      'SELECT id, nombre, descripcion FROM departamentos WHERE id = $1',
      [id]
    );
    return rows.length ? rows[0] : null;
  }

  async findAll() {
    const { rows } = await this.pool.query(
      'SELECT id, nombre, descripcion FROM departamentos ORDER BY id'
    );
    return rows;
  }
}
