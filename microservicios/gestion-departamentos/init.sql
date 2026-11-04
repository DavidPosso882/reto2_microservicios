-- Schema for the departamentos service (Reto 2).
-- Applied automatically by docker-compose init scripts and usable locally.

CREATE TABLE IF NOT EXISTS departamentos (
    id          VARCHAR(255) PRIMARY KEY,
    nombre      VARCHAR(255) NOT NULL,
    descripcion TEXT         NOT NULL
);