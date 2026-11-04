import jwt from 'jsonwebtoken';

/**
 * Edge authentication and authorization (Reto 5, Step 2).
 *
 * Reto 5 decision: JWT validation lives in ONE component — this gateway — so
 * upstream services keep plain HTTP inside the Docker network and the edge
 * proves every request before proxying it:
 *
 *   - `authenticate`: requires a valid Bearer access JWT (HS256, the shared
 *     JWT_SECRET, same one auth-service signs with). Missing, expired,
 *     foreign-key or malformed tokens -> 401 { status, error } envelope.
 *     On success attaches `req.user` = { sub, role }.
 *   - `authorizeService(servicio)`: RBAC + ownership. ADMIN bypasses all.
 *     USER is read-only (GET/HEAD) on the business services; writes are
 *     denied with 403 except the ownership rule: USER may PUT
 *     /perfiles/:empleadoId only when :empleadoId is its own sub.
 *     Denials are always 403 (never 401: the token already proved identity,
 *     this is an authorization refusal) and are checked AFTER `authenticate`.
 *   - `forwardIdentity`: for the protected /auth mount (change-password) it
 *     re-attaches the gateway-verified identity as trusted headers
 *     X-User-Id / X-User-Role, overwriting whatever the client sent.
 *   - Reset tokens (claim `type: 'RESET_PASSWORD'`) never authenticate:
 *     they are one-shot recovery values, not access credentials.
 */

const WRITE_METHODS = new Set(['POST', 'PUT', 'DELETE', 'PATCH']);

/**
 * Reads the shared HMAC secret lazily (docker-compose injects it at source;
 * tests set it after import). Returns null when unset so the gateway answers
 * with a controlled 500 envelope instead of crashing or failing open.
 */
export function jwtSecret() {
  const secret = process.env.JWT_SECRET;
  return secret && String(secret).trim() !== '' ? String(secret).trim() : null;
}

/**
 * Extracts the raw bearer token from the Authorization header, or null.
 * Scheme is case-insensitive ('Bearer', 'bearer'); the header must carry exactly
 * one scheme plus a non-empty token.
 */
function bearerToken(req) {
  const header = (req.get('Authorization') || '').trim();
  const match = /^bearer\s+(.+)$/i.exec(header);
  return match ? match[1].trim() : null;
}

/**
 * Verifies an access JWT and reduces its payload to the edge identity
 * { sub, role }. Any failure (bad signature, expired, wrong key, reset-type
 * token, missing sub/role) resolves to null — never throws.
 */
export function verifyAccessToken(token) {
  const secret = jwtSecret();
  if (!token || !secret) {
    return null;
  }
  try {
    const payload = jwt.verify(token, secret, { algorithms: ['HS256'] });
    if (!payload || typeof payload !== 'object') {
      return null;
    }
    if (typeof payload.sub !== 'string' || payload.sub.trim() === '') {
      return null;
    }
    if (payload.role !== 'ADMIN' && payload.role !== 'USER') {
      return null;
    }
    if (payload.type) {
      return null;
    }
    return { sub: payload.sub, role: payload.role };
  } catch {
    return null;
  }
}

/**
 * Express middleware: the gate for everything mounted after it (protected
 * /auth and the five business services). Missing/invalid token -> 401 with
 * the house envelope; valid token -> attaches req.user and continues.
 */
export function authenticate(req, res, next) {
  // Fallo ruidoso ante una configuración faltante (compose SIEMPRE la inyecta):
  // un 401 genérico escondería el problema de configuración del borde.
  if (!jwtSecret()) {
    return res
      .status(500)
      .json({ status: 500, error: 'La variable de entorno JWT_SECRET no está configurada' });
  }
  const user = verifyAccessToken(bearerToken(req));
  if (!user) {
    return res
      .status(401)
      .json({ status: 401, error: 'Se requiere un token de acceso válido en el header Authorization' });
  }
  req.user = user;
  next();
}

/**
 * First path segment (payload resource id), query string and decoding
 * applied; null when the route has no segment (mounting /perfiles bare).
 */
function firstSegmentOf(ruta) {
  const sinQuery = ruta.split('?')[0];
  const segmento = sinQuery.split('/').filter(Boolean)[0];
  if (!segmento) {
    return null;
  }
  try {
    return decodeURIComponent(segmento);
  } catch {
    return null;
  }
}

/**
 * RBAC + ownership for a business-service mount (used after `authenticate`).
 *
 *   ADMIN      : full access to ${servicio}.
 *   USER GET/HEAD : read-only, allowed.
 *   USER writes   : 403 unless PUT /perfiles/:empleadoId is its own perfil.
 *
 * The 403 envelope leaks nothing about the resource; it only says the
 * caller is not authorized for that write.
 */
export function authorizeService(servicio) {
  return (req, res, next) => {
    if (req.user.role === 'ADMIN') {
      return next();
    }
    if (!WRITE_METHODS.has(req.method)) {
      return next();
    }
    if (servicio === 'perfiles' && req.method === 'PUT') {
      const destino = firstSegmentOf(req.path);
      if (destino && destino === req.user.sub) {
        return next();
      }
    }
    return res.status(403).json({
      status: 403,
      error: `No tiene permisos para escribir en el servicio de ${servicio}`,
    });
  };
}

/**
 * Protected /auth mount helper (change-password): auth-service resolves the
 * identity from the X-User-Id / X-User-Role headers the gateway forwards.
 * The gateway owns verification, so the headers are always overwritten with
 * the verified identity — a client can never smuggle an identity through.
 */
export function forwardIdentity(req, res, next) {
  req.headers['x-user-id'] = req.user.sub;
  req.headers['x-user-role'] = req.user.role;
  next();
}
