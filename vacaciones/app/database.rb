# frozen_string_literal: true

module Vacaciones
  # Single shared Postgres connection (the service is a low-traffic
  # educational microservice; one connection keeps transactions simple).
  class Database
    def initialize(config)
      @config = config
    end

    def connection
      require 'pg'
      @connection ||= PG.connect(
        host: @config.db_host,
        port: @config.db_port,
        dbname: @config.db_name,
        user: @config.db_user,
        password: @config.db_password
      )
    end

    def with_transaction
      conn = connection
      conn.transaction do
        yield conn
      end
    end

    # Idempotent schema bootstrap: same DDL as init.sql, so the service works
    # even when the database was created without the init script mounted.
    ENSURE_SCHEMA_SQL = <<~SQL
      CREATE TABLE IF NOT EXISTS vacaciones (
        id TEXT PRIMARY KEY,
        empleado_id TEXT NOT NULL,
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE NOT NULL,
        estado TEXT NOT NULL,
        fecha_creacion TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE INDEX IF NOT EXISTS idx_vacaciones_empleado ON vacaciones (empleado_id);
      CREATE TABLE IF NOT EXISTS empleados_locales (
        empleado_id TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        nombre TEXT NOT NULL DEFAULT '',
        estado TEXT NOT NULL,
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
      );
      CREATE TABLE IF NOT EXISTS eventos_procesados (
        id TEXT PRIMARY KEY,
        procesado_en TIMESTAMPTZ NOT NULL DEFAULT now()
      );
    SQL

    def ensure_schema
      connection.exec(ENSURE_SCHEMA_SQL)
    end
  end
end
