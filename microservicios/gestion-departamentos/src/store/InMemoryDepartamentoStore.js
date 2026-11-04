import { DuplicateError } from '../errors.js';

/**
 * In-memory implementation of the departamento store.
 *
 * Used by the test suite to exercise routing and validation without a live
 * PostgreSQL database. It implements the same contract as
 * `PgDepartamentoStore` so the service stays store-agnostic.
 */
export class InMemoryDepartamentoStore {
  constructor() {
    this.rows = new Map();
  }

  async create(departamento) {
    if (this.rows.has(departamento.id)) {
      throw new DuplicateError(`El departamento con id ${departamento.id} ya existe`);
    }
    this.rows.set(departamento.id, { ...departamento });
    return { ...departamento };
  }

  async findById(id) {
    const row = this.rows.get(id);
    return row ? { ...row } : null;
  }

  async findAll() {
    return Array.from(this.rows.values()).map((row) => ({ ...row }));
  }
}
