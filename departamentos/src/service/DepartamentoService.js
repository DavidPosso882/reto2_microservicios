import { ValidationError, NotFoundError } from '../errors.js';

/**
 * Business logic for departamentos.
 *
 * Validates input, enforces uniqueness, and maps not-found results to
 * `NotFoundError`. Persistence is delegated to an injectable store so the
 * service is easy to test without a database.
 */
export class DepartamentoService {
  constructor(store) {
    this.store = store;
  }

  async register(departamento) {
    const id = departamento?.id;
    const nombre = departamento?.nombre;
    const descripcion = departamento?.descripcion;

    if (!isPresent(id) || !isPresent(nombre) || !isPresent(descripcion)) {
      throw new ValidationError('Los campos id, nombre y descripcion son obligatorios');
    }

    return this.store.create({ id, nombre, descripcion });
  }

  async getById(id) {
    const found = await this.store.findById(id);
    if (!found) {
      throw new NotFoundError(`El departamento con id ${id} no existe`);
    }
    return found;
  }

  async list() {
    return this.store.findAll();
  }
}

function isPresent(value) {
  return value !== undefined && value !== null && String(value).trim() !== '';
}
