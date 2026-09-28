import express from 'express';
import { ValidationError } from '../errors.js';
import { UsuarioService } from '../service/UsuarioService.js';

/**
 * Builds the auth router (Reto 5).
 *
 * Failure responses use the house JSON envelope `{ status, error }`. Reset
 * tokens never appear in any HTTP response: they travel only through the
 * `usuario.creado` / `usuario.recuperacion` events consumed by
 * notificaciones-service (the simulated email channel). No HTTP response ever
 * returns a password: the bootstrap seed response exposes only the public
 * account view, and the plaintext password is consumed in-memory by the
 * service (hashed before persistence) so no response or event can deliver it.
 *
 * Routes are public by design: the API gateway (Reto 5 step 2) will whitelist
 * /auth/* from JWT validation, per the PDF onboarding flow.
 *
 * @param {object} deps
 * @param {UsuarioService} deps.service
 * @returns {import('express').Router}
 */
export function createAuthRouter({ service }) {
  const router = express.Router();

  router.post('/bootstrap', async (req, res, next) => {
    try {
      const { email, password } = req.body || {};
      if (!email || !password) {
        throw new ValidationError('email y password son obligatorios');
      }
      const admin = await service.bootstrapAdmin({ email, password });
      // Public account view only: service.bootstrapAdmin never returns
      // passwordHash and the router already discarded the plaintext password.
      res.status(201).json(admin);
    } catch (err) {
      next(err);
    }
  });

  router.post('/login', async (req, res, next) => {
    try {
      const { email, password } = req.body || {};
      const resultado = await service.login({ email, password });
      res.status(200).json({
        accessToken: resultado.token,
        tokenType: 'Bearer',
        expiresIn: Number(process.env.JWT_ACCESS_TTL_MINUTES || 60) * 60,
        usuario: resultado.usuario,
      });
    } catch (err) {
      next(err);
    }
  });

  router.post('/recover-password', async (req, res, next) => {
    try {
      const { email } = req.body || {};
      const resultado = await service.recoverPassword({ email });
      res.status(200).json({
        ...resultado,
        message: 'Si el email está registrado, se envió un enlace de recuperación',
      });
    } catch (err) {
      next(err);
    }
  });

  router.post('/reset-password', async (req, res, next) => {
    try {
      const { token, nuevaPassword } = req.body || {};
      const resultado = await service.resetPassword({ token, nuevaPassword });
      res.status(200).json(resultado);
    } catch (err) {
      next(err);
    }
  });

  router.post('/change-password', async (req, res, next) => {
    try {
      const identity = await extraerIdentidad(req);
      if (!identity) {
        return res.status(401).json({
          status: 401,
          error: 'Se requiere un token de acceso válido en el header Authorization',
        });
      }
      const { passwordActual, passwordNueva } = req.body || {};
      const resultado = await service.cambiarPassword(identity, {
        passwordActual,
        passwordNueva,
      });
      res.status(200).json(resultado);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

/**
 * Resolves the authenticated identity for change-password.
 *
 * Primary path (Reto 5 decision): the gateway validates the access JWT and
 * forwards identity as trusted headers X-User-Id / X-User-Role.
 * Direct-access fallback: verifies a bearer access JWT with the same HMAC
 * secret, so the endpoint also works in front of the gateway (tests, local).
 * A reset token (type: RESET_PASSWORD) never authenticates this route.
 */
export async function extraerIdentidad(req, { jwtSecret = process.env.JWT_SECRET } = {}) {
  const hdrId = req.get('X-User-Id');
  const hdrRole = req.get('X-User-Role');

  if (hdrId && (hdrRole === 'ADMIN' || hdrRole === 'USER')) {
    return { id: hdrId, role: hdrRole };
  }

  const auth = req.get('Authorization') || '';
  const [scheme, token] = auth.split(' ');
  if (scheme !== 'Bearer' || !token || !jwtSecret) {
    return null;
  }
  const payload = await verificarLocal(token, jwtSecret);
  if (!payload || !payload.sub || payload.type) {
    return null;
  }
  return { id: payload.sub, role: payload.role };
}

async function verificarLocal(token, secret) {
  // Dynamic import keeps the jwt dependency off the critical path; signature
  // or expiry failures resolve to null instead of throwing.
  const { default: jwt } = await import('jsonwebtoken');
  try {
    return jwt.verify(token, secret, { algorithms: ['HS256'] });
  } catch {
    return null;
  }
}
