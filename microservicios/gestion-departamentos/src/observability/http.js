import { logger } from './logger.js';

/** Access log JSON with method, path, status and duration (no query/body). */
export function accessLogMiddleware(req, res, next) {
  const started = process.hrtime.bigint();
  res.on('finish', () => {
    const durationMs = Number(process.hrtime.bigint() - started) / 1e6;
    logger.info('http_request', {
      method: req.method,
      path: req.path,
      status: res.statusCode,
      durationMs: Math.round(durationMs * 1000) / 1000,
    });
  });
  next();
}
