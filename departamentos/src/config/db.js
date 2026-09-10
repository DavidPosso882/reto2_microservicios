import pg from 'pg';

const { Pool } = pg;

/**
 * Builds a pg connection pool from environment variables.
 *
 * Expected variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
 */
export function createPool() {
  return new Pool({
    host: process.env.DB_HOST || 'localhost',
    port: Number(process.env.DB_PORT || 5432),
    database: process.env.DB_NAME || 'departamentos',
    user: process.env.DB_USER || 'postgres',
    password: process.env.DB_PASSWORD || '',
    max: 10,
    idleTimeoutMillis: 30000,
  });
}
