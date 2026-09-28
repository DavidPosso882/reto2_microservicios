import { AppError, CredencialesInvalidasError, NotFoundError, TokenInvalidoError, ValidationError } from '../errors.js';
import {
  hashPassword,
  issueAccessToken,
  issueResetToken,
  verifyPassword,
  verifyToken,
} from '../tokens.js';
import { validarPoliticaPassword } from '../passwordPolicy.js';

export const ESTADO_ACTIVA = 'ACTIVA';
export const ESTADO_SUSPENDIDA_TEMPORAL = 'SUSPENDIDA_TEMPORAL';
export const ESTADO_DESACTIVADA_PERMANENTE = 'DESACTIVADA_PERMANENTE';
const ESTADOS_VALIDOS = [
  ESTADO_ACTIVA,
  ESTADO_SUSPENDIDA_TEMPORAL,
  ESTADO_DESACTIVADA_PERMANENTE,
];

export const ROL_ADMIN = 'ADMIN';
export const ROL_USER = 'USER';

/**
 * Account store contract (asynchronous API shared by both implementations):
 *
 *   contarUsuarios() -> number
 *   crear({id, email, passwordHash, role, estado}) -> Promise
 *   actualizarEstado(id, estado) -> Promise
 *   actualizarPasswordHash(id, passwordHash) -> Promise
 *   buscarPorId(id) -> usuario | null
 *   buscarPorEmail(email) -> usuario | null
 *   procesados(id) -> boolean  (event dedup ledger)
 *   marcarProcesado(id) -> Promise
 */
export class UsuarioService {
  constructor(store, { eventPublisher = null } = {}) {
    this.store = store;
    this.eventPublisher = eventPublisher;
  }

  setEventPublisher(publisher) {
    this.eventPublisher = publisher;
  }

  async _publicarEvento(type, data) {
    if (this.eventPublisher) {
      try {
        await this.eventPublisher(type, data);
      } catch (err) {
        // Publishing a lifecycle event must not fail the HTTP/crud operation:
        // the broker consumer side is what retries/dedups.
        // eslint-disable-next-line no-console
        console.warn(`[auth] No se pudo publicar ${type}: ${err.message}`);
      }
    }
  }

  async bootstrapAdmin({ email, password }) {
    const existentes = await this.store.contarUsuarios();
    if (existentes > 0) {
      throw new ValidationError(
        'El bootstrap solo está disponible cuando la tabla de usuarios está vacía (el ADMIN semilla ya existe)'
      );
    }
    const errorPolitica = validarPoliticaPassword(password);
    if (errorPolitica) {
      throw new ValidationError(errorPolitica);
    }
    const passwordHash = await hashPassword(password);
    const admin = {
      id: 'ADMIN',
      email,
      passwordHash,
      role: ROL_ADMIN,
      estado: ESTADO_ACTIVA,
    };
    await this.store.crear(admin);
    return { id: admin.id, email: admin.email, role: admin.role, estado: admin.estado };
  }

  async login({ email, password }) {
    if (!email || !password) {
      throw new ValidationError('email y password son obligatorios');
    }
    const usuario = await this.store.buscarPorEmail(String(email).trim().toLowerCase());
    if (
      !usuario ||
      usuario.estado === ESTADO_DESACTIVADA_PERMANENTE ||
      usuario.estado === ESTADO_SUSPENDIDA_TEMPORAL ||
      !usuario.passwordHash
    ) {
      throw new CredencialesInvalidasError();
    }
    const ok = await verifyPassword(String(password), usuario.passwordHash);
    if (!ok) {
      throw new CredencialesInvalidasError();
    }
    const token = issueAccessToken(usuario);
    return { token, usuario: publicUsuario(usuario) };
  }

  async recoverPassword({ email }) {
    if (!email) {
      throw new ValidationError('email es obligatorio');
    }
    const usuario = await this.store.buscarPorEmail(String(email).trim().toLowerCase());
    // Uniform 200 even when the email is unknown: never leak account existence.
    if (!usuario) {
      return { enviado: true };
    }
    if (usuario.estado === ESTADO_DESACTIVADA_PERMANENTE) {
      // A permanently disabled account cannot recover its password.
      return { enviado: true };
    }
    const resetToken = issueResetToken(usuario);
    await this._publicarEvento('usuario.recuperacion', {
      email: usuario.email,
      empleadoId: usuario.id,
      resetToken,
      expiracion: '30min',
    });
    return { enviado: true };
  }

  async cambiarPassword(user, { passwordActual, passwordNueva }) {
    if (!user || !user.id) {
      throw new TokenInvalidoError('Se requiere un token de acceso válido');
    }
    if (!passwordActual || !passwordNueva) {
      throw new ValidationError('passwordActual y passwordNueva son obligatorias');
    }
    const usuario = await this.store.buscarPorId(user.id);
    if (!usuario) {
      throw new NotFoundError('Usuario no encontrado');
    }
    if (usuario.estado === ESTADO_DESACTIVADA_PERMANENTE) {
      throw new CredencialesInvalidasError('La cuenta está desactivada permanentemente');
    }
    const okActual = await verifyPassword(String(passwordActual), usuario.passwordHash);
    if (!okActual) {
      throw new ValidationError('La contraseña actual no es correcta');
    }
    const errorPolitica = validarPoliticaPassword(String(passwordNueva));
    if (errorPolitica) {
      throw new ValidationError(errorPolitica);
    }
    const passwordHash = await hashPassword(String(passwordNueva));
    await this.store.actualizarPasswordHash(usuario.id, passwordHash);
    return { cambiada: true, usuario: publicUsuario(usuario) };
  }

  /**
   * Applies a reset token: validates signature/type/expiry, enforces the
   * password policy on the new password, persists the BCrypt hash and
   * activates the account (first activation or recovery).
   *
   * A permanently disabled account (DESACTIVADA_PERMANENTE) is rejected with
   * a uniform `TokenInvalidoError` before any state or password change, so a
   * reset token can never reactivate it and `cuenta.activada` is never
   * published for it.
   */
  async resetPassword({ token, nuevaPassword }) {
    if (!token || !nuevaPassword) {
      throw new ValidationError('token y nuevaPassword son obligatorios');
    }
    const payload = verifyToken(String(token), { requireType: 'RESET_PASSWORD' });
    if (!payload || !payload.sub) {
      throw new TokenInvalidoError('El token es inválido o expiró');
    }
    const usuario = await this.store.buscarPorId(payload.sub);
    if (!usuario) {
      throw new TokenInvalidoError('El token es inválido o expiró');
    }
    if (usuario.estado === ESTADO_DESACTIVADA_PERMANENTE) {
      // Uniform TokenInvalidoError (no leak): a permanently disabled account
      // cannot be reactivated with a reset token, and cuenta.activada is
      // never published for it.
      throw new TokenInvalidoError('El token es inválido o expiró');
    }
    const errorPolitica = validarPoliticaPassword(String(nuevaPassword));
    if (errorPolitica) {
      throw new ValidationError(errorPolitica);
    }
    const passwordHash = await hashPassword(String(nuevaPassword));
    await this.store.actualizarPasswordHash(usuario.id, passwordHash);
    const estadoAnterior = usuario.estado;
    if (usuario.estado !== ESTADO_ACTIVA) {
      await this.store.actualizarEstado(usuario.id, ESTADO_ACTIVA);
    }
    if (estadoAnterior !== ESTADO_ACTIVA) {
      await this._publicarEvento('cuenta.activada', {
        email: usuario.email,
        empleadoId: usuario.id,
        motivo: 'ESTABLECIMIENTO_PASSWORD',
      });
    }
    return { actualizada: true, usuario: publicUsuario(usuario) };
  }

  /* ── Event-driven account lifecycle (consumed events) ── */

  async aplicarEmpleadoCreado(data) {
    const existe = await this.store.buscarPorId(data.id);
    if (existe) {
      return { creado: false, motivo: 'La cuenta ya existe (evento duplicado o replay)' };
    }
    const cuenta = {
      id: data.id,
      email: String(data.email).trim().toLowerCase(),
      passwordHash: null, // sin contraseña válida hasta el reset
      role: ROL_USER,
      estado: ESTADO_SUSPENDIDA_TEMPORAL,
    };
    await this.store.crear(cuenta);
    const resetToken = issueResetToken(cuenta);
    await this._publicarEvento('usuario.creado', {
      empleadoId: cuenta.id,
      email: cuenta.email,
      nombre: data.nombre,
      apellido: data.apellido,
      resetToken,
    });
    return { creado: true };
  }

  async aplicarEmpleadoRetirado(data) {
    const cuenta = await this.store.buscarPorId(data.id);
    if (!cuenta) {
      return { aplicado: false, motivo: 'No existe cuenta para el empleado retirado' };
    }
    await this.store.actualizarEstado(cuenta.id, ESTADO_DESACTIVADA_PERMANENTE);
    await this._publicarEvento('cuenta.desactivada', {
      email: cuenta.email,
      empleadoId: cuenta.id,
      motivo: 'RETIRO',
      permanente: true,
    });
    return { aplicado: true };
  }

  async aplicarVacacionesIniciadas(data) {
    const cuenta = await this.store.buscarPorId(data.empleadoId);
    if (!cuenta) {
      return { aplicado: false, motivo: 'No existe cuenta para el empleado' };
    }
    if (cuenta.estado === ESTADO_DESACTIVADA_PERMANENTE) {
      return { aplicado: false, motivo: 'La cuenta ya está desactivada permanentemente' };
    }
    if (cuenta.estado === ESTADO_SUSPENDIDA_TEMPORAL) {
      // Ya suspendida: no hay cambio de estado, pero notificaciones siempre
      // debe recibir la desactivación (idempotencia con aviso).
      await this._publicarEvento('cuenta.desactivada', {
        email: cuenta.email,
        empleadoId: cuenta.id,
        motivo: 'VACACIONES',
        permanente: false,
      });
      return { aplicado: false, motivo: 'Ya suspendida; cuenta.desactivada reenviada' };
    }
    await this.store.actualizarEstado(cuenta.id, ESTADO_SUSPENDIDA_TEMPORAL);
    await this._publicarEvento('cuenta.desactivada', {
      email: cuenta.email,
      empleadoId: cuenta.id,
      motivo: 'VACACIONES',
      permanente: false,
    });
    return { aplicado: true };
  }

  async aplicarVacacionesFinalizadas(data) {
    const cuenta = await this.store.buscarPorId(data.empleadoId);
    if (!cuenta) {
      return { aplicado: false, motivo: 'No existe cuenta para el empleado' };
    }
    // Caso borde evaluable: retiro durante vacaciones → la cuenta quedó
    // DESACTIVADA_PERMANENTE y NO se reactiva.
    if (cuenta.estado === ESTADO_DESACTIVADA_PERMANENTE) {
      return { aplicado: false, motivo: 'Cuenta con baja permanente: no se reactiva' };
    }
    if (cuenta.estado === ESTADO_ACTIVA) {
      return { aplicado: false, motivo: 'La cuenta ya está activa' };
    }
    await this.store.actualizarEstado(cuenta.id, ESTADO_ACTIVA);
    await this._publicarEvento('cuenta.activada', {
      email: cuenta.email,
      empleadoId: cuenta.id,
      motivo: 'FIN_VACACIONES',
    });
    return { aplicado: true };
  }
}

/**
 * Public view of a user: never includes passwordHash.
 */
export function publicUsuario(usuario) {
  return {
    id: usuario.id,
    email: usuario.email,
    role: usuario.role,
    estado: usuario.estado,
  };
}
