import { readFileSync } from 'node:fs';

/**
 * Secret resolution (Proyecto Final — "cero secretos en el repositorio").
 *
 * Convention shared by every service of the ecosystem:
 *   1. NAME_FILE set  -> read the secret from that file (Docker Compose
 *      secrets mount it at /run/secrets/<name>); surrounding whitespace and
 *      the trailing newline are trimmed.
 *   2. otherwise NAME -> plain environment variable (local runs and tests).
 *   3. neither        -> empty string: the caller decides how to fail.
 *
 * File contents are cached per path: the secret is read once, not per request.
 */
const cache = new Map();

export function readSecret(name, env = process.env) {
  const file = env[`${name}_FILE`];
  if (file && String(file).trim() !== '') {
    const path = String(file).trim();
    if (!cache.has(path)) {
      cache.set(path, readFileSync(path, 'utf8').trim());
    }
    return cache.get(path);
  }
  const value = env[name];
  return value === undefined || value === null ? '' : String(value).trim();
}

/** Test hook: forget cached files (tests rewrite the same temp path). */
export function _clearSecretCacheForTests() {
  cache.clear();
}
