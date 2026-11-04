-- auth-service: esquema inicial (migración de una sola vía).
-- Se ejecuta automáticamente por docker-entrypoint-initdb.d y, además, el
-- servicio aplica el mismo DDL idempotente al arrancar (EnsureSchema).

-- Cuentas de acceso del ecosistema (una por empleado + el ADMIN semilla).
CREATE TABLE IF NOT EXISTS usuarios (
    id TEXT PRIMARY KEY,                -- empleadoId (E001...) o 'ADMIN' (bootstrap)
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,                 -- BCrypt; NULL = cuenta sin activar (sin contraseña válida)
    role TEXT NOT NULL,                 -- ADMIN | USER
    estado TEXT NOT NULL,               -- ACTIVA | SUSPENDIDA_TEMPORAL | DESACTIVADA_PERMANENTE
    fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (email);

-- Deduplicación de eventos del envelope (id del envelope como clave).
CREATE TABLE IF NOT EXISTS eventos_procesados (
    id TEXT PRIMARY KEY,
    procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
