-- perfiles-service: esquema inicial (migración de una sola vía).
-- Se ejecuta automáticamente por docker-entrypoint-initdb.d y, además, el
-- servicio aplica el mismo DDL idempotente al arrancar (EnsureSchema).

CREATE TABLE IF NOT EXISTS perfiles (
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	empleado_id TEXT UNIQUE NOT NULL,
	nombre TEXT NOT NULL DEFAULT '',
	apellido TEXT NOT NULL DEFAULT '',
	email TEXT NOT NULL DEFAULT '',
	telefono TEXT NOT NULL DEFAULT '',
	direccion TEXT NOT NULL DEFAULT '',
	ciudad TEXT NOT NULL DEFAULT '',
	biografia TEXT NOT NULL DEFAULT '',
	archivado BOOL NOT NULL DEFAULT FALSE,
	fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now(),
	fecha_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eventos_procesados (
	id TEXT PRIMARY KEY,
	procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
