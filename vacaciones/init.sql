-- vacaciones-service: esquema inicial (migración de una sola vía).
-- Se ejecuta automáticamente por docker-entrypoint-initdb.d y, además, el
-- servicio aplica el mismo DDL idempotente al arrancar (EnsureSchema).

-- Períodos de vacaciones gestionados por REST.
CREATE TABLE IF NOT EXISTS vacaciones (
	id TEXT PRIMARY KEY,                -- V-AAAA-NNNN (generado por el servidor)
	empleado_id TEXT NOT NULL,
	fecha_inicio DATE NOT NULL,
	fecha_fin DATE NOT NULL,
	estado TEXT NOT NULL,               -- PROGRAMADA | CANCELADA (Reto 4)
	fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vacaciones_empleado ON vacaciones (empleado_id);

-- Réplica local de empleados (opción b: validación por eventos, sin REST saliente).
CREATE TABLE IF NOT EXISTS empleados_locales (
	empleado_id TEXT PRIMARY KEY,
	email TEXT NOT NULL,
	nombre TEXT NOT NULL DEFAULT '',
	estado TEXT NOT NULL,               -- ACTIVO | PENDIENTE_VALIDACION | RETIRADO
	actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Deduplicación de eventos del envelope (id del envelope como clave).
CREATE TABLE IF NOT EXISTS eventos_procesados (
	id TEXT PRIMARY KEY,
	procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
