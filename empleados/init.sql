-- ============================================================
-- Script de inicialización de la base de datos del servicio de
-- empleados (Reto 2).
--
-- Crea la tabla "empleado" con restricciones UNIQUE a nivel de
-- base de datos sobre email y numero_empleado. Estas restricciones
-- son la garantía REAL contra las carreras de concurrencia: aunque
-- dos requests pasen las validaciones de la aplicación, el segundo
-- INSERT fallará por violación de unicidad.
--
-- NOTA: los nombres de columna usan snake_case para coincidir con la
-- estrategia de nombres por defecto de Hibernate (spring.jpa.hibernate
-- .naming.physical-strategy), ya que el esquema se gestiona con este
-- script (spring.jpa.hibernate.ddl-auto=none).
-- ============================================================

CREATE TABLE IF NOT EXISTS empleado (
    id               VARCHAR(255) NOT NULL,
    nombre           VARCHAR(255) NOT NULL,
    apellido         VARCHAR(255) NOT NULL,
    email            VARCHAR(255) NOT NULL,
    numero_empleado  VARCHAR(255) NOT NULL,
    cargo            VARCHAR(255) NOT NULL,
    area             VARCHAR(255) NOT NULL,
    departamento_id  VARCHAR(255) NOT NULL,
    fecha_ingreso    VARCHAR(255) NOT NULL,
    estado           VARCHAR(20)  NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uk_empleado_email UNIQUE (email),
    CONSTRAINT uk_empleado_numero_empleado UNIQUE (numero_empleado)
);
