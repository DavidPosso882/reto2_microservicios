import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import { randomUUID } from 'node:crypto';
import { AppError, TokenInvalidoError } from './errors.js';

/**
 * Token issuing and verification (Reto 5 structures).
 *
 * Access JWT  : { sub, role: ADMIN|USER, iat, exp } — HMAC SHA-256 (HS256).
 * Reset token : { sub, type: RESET_PASSWORD, iat, exp } — short lived
 *               (stateless, Option A of the PDF), signed with the same secret
 *               but carrying the type claim that access tokens never carry.
 *
 * Passwords are never placed inside any token; they are stored hashed with
 * BCrypt (bcryptjs keeps the Docker image pure-JS and architecture-free).
 */

const ACCESS_TTL_MINUTES = Number(process.env.JWT_ACCESS_TTL_MINUTES || 60);
const RESET_TTL_MINUTES = Number(process.env.JWT_RESET_TTL_MINUTES || 30);
const BCRYPT_ROUNDS = Number(process.env.BCRYPT_ROUNDS || 10);

/**
 * Resolves the HMAC secret at call time (not at import time) so tests can
 * configure JWT_SECRET after import and before issuing/verifying.
 */
function secret() {
  const s = process.env.JWT_SECRET;
  if (!s || String(s).trim() === '') {
    throw new AppError(500, 'La variable de entorno JWT_SECRET no está configurada');
  }
  return s;
}

export function issueAccessToken(user) {
  return jwt.sign(
    { sub: user.id, role: user.role },
    secret(),
    { algorithm: 'HS256', expiresIn: `${ACCESS_TTL_MINUTES}m` }
  );
}

/**
 * Activación y recuperación comparten la estructura { sub, type: RESET_PASSWORD }.
 */
export function issueResetToken(user) {
  return jwt.sign(
    { sub: user.id, type: 'RESET_PASSWORD' },
    secret(),
    { algorithm: 'HS256', expiresIn: `${RESET_TTL_MINUTES}m` }
  );
}

/**
 * Verifies a signed token and returns its decoded payload, or null when the
 * signature/expiry does not hold. `options.requireType` keeps access tokens
 * from being replayed as reset tokens and vice versa.
 */
export function verifyToken(token, { requireType = null } = {}) {
  try {
    const payload = jwt.verify(token, secret(), { algorithms: ['HS256'] });
    if (requireType && payload.type !== requireType) {
      return null;
    }
    if (!requireType && payload.type) {
      return null; // reset/typed token cannot be used as an access token
    }
    return payload;
  } catch {
    return null;
  }
}

export function hashPassword(plain) {
  return bcrypt.hash(plain, BCRYPT_ROUNDS);
}

export function verifyPassword(plain, passwordHash) {
  return bcrypt.compare(plain, passwordHash || '');
}

/**
 * Envelope builder for every event this service publishes
 * (CATALOGO_EVENTOS.md section 1): UUID id, topic routing key = `type`,
 * version 1.0, UTC ISO-8601 `occurredAt`, producer name, non-null data.
 */
export function buildEnvelope(type, producer, data) {
  return {
    id: randomUUID(),
    type,
    version: '1.0',
    occurredAt: new Date().toISOString(),
    producer,
    data,
  };
}
