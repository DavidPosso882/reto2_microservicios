import pg from 'pg';
import { readSecret } from './secrets.js';

const { Pool } = pg;

/**
 * Builds a pg connection pool from environment variables.
 *
 * Expected variables: DB_HOST, DB_PORT, DB_NAME, DB_USER and DB_PASSWORD_FILE
 * (Docker secret) or DB_PASSWORD.
 */
export function createPool() {
  return new Pool({
    host: process.env.DB_HOST || 'localhost',
    port: Number(process.env.DB_PORT || 5432),
    database: process.env.DB_NAME || 'auth_db',
    user: process.env.DB_USER || 'postgres',
    // DB_PASSWORD_FILE (Docker secret) o DB_PASSWORD; nunca un valor fijo en código.
    password: readSecret('DB_PASSWORD'),
    max: 10,
    idleTimeoutMillis: 30000,
  });
}
