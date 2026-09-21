// Package postgres implements store.Store on top of lib/pq.
//
// Event application is atomic and idempotent: the effect and the dedup mark
// (eventos_procesados) live in the same transaction, and every effect is a
// safe upsert so re-delivered messages cannot duplicate rows or lose data.
package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	_ "github.com/lib/pq"

	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

// Store is the Postgres-backed implementation of store.Store.
type Store struct {
	db *sql.DB
}

// New opens the connection pool and pins the driver.
func New(dsn string) (*Store, error) {
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, fmt.Errorf("open postgres: %w", err)
	}
	// One consumer goroutine plus a low-traffic REST API: small pool is enough.
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)
	return &Store{db: db}, nil
}

// EnsureSchema applies the single-way migration (same DDL as init.sql).
// Safe to run on every start: everything is IF NOT EXISTS.
func (s *Store) EnsureSchema(ctx context.Context) error {
	const ddl = `
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
`
	if _, err := s.db.ExecContext(ctx, ddl); err != nil {
		return fmt.Errorf("ensure schema: %w", err)
	}
	return nil
}

// Close closes the pool.
func (s *Store) Close() error { return s.db.Close() }

// ApplyEvent applies the event effect and records the event id inside ONE
// transaction (ACK-after-persist contract of CATALOGO_EVENTOS.md section 2).
//
// applied=false means: duplicate id (no effect, safe ACK) or unknown type
// (ignored, marked to avoid requeue loops).
func (s *Store) ApplyEvent(ctx context.Context, ev domain.Event) (bool, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return false, fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }() // no-op after commit

	// Dedup gate: insert the id first; if it already exists the event was
	// processed before and we must not apply the effect again.
	res, err := tx.ExecContext(ctx,
		`INSERT INTO eventos_procesados (id) VALUES ($1) ON CONFLICT (id) DO NOTHING`,
		ev.ID)
	if err != nil {
		return false, fmt.Errorf("mark eventos_procesados: %w", err)
	}
	n, err := res.RowsAffected()
	if err != nil {
		return false, fmt.Errorf("rows affected eventos_procesados: %w", err)
	}
	if n == 0 {
		return false, nil // duplicate event id → no effect
	}

	switch ev.Type {
	case "empleado.creado":
		err = applyEmpleadoCreado(ctx, tx, ev.Data)
	case "empleado.actualizado":
		err = applyEmpleadoActualizado(ctx, tx, ev.Data)
	case "empleado.retirado":
		err = applyEmpleadoRetirado(ctx, tx, ev.Data)
	default:
		// Unknown type: keep it marked as processed and ignore it.
		return true, nil
	}
	if err != nil {
		return false, err
	}
	if err := tx.Commit(); err != nil {
		return false, fmt.Errorf("commit event %s: %w", ev.ID, err)
	}
	return true, nil
}

// applyEmpleadoCreado creates the default profile (empty contact fields), or
// refreshes the replicated identity fields if a profile already exists
// (never duplicates: empleado_id is UNIQUE).
func applyEmpleadoCreado(ctx context.Context, tx *sql.Tx, d domain.EventData) error {
	if _, err := tx.ExecContext(ctx, `
INSERT INTO perfiles (empleado_id, nombre, apellido, email)
VALUES ($1, $2, $3, $4)
ON CONFLICT (empleado_id) DO UPDATE
SET nombre = EXCLUDED.nombre,
    apellido = EXCLUDED.apellido,
    email = EXCLUDED.email,
    fecha_actualizacion = now()
`, d.ID, d.Nombre, d.Apellido, d.Email); err != nil {
		return fmt.Errorf("apply empleado.creado: %w", err)
	}
	return nil
}

// applyEmpleadoActualizado syncs ONLY nombre, apellido, email, and never
// touches telefono/direccion/ciudad/biografia. Archived profiles are left
// untouched. If no profile exists, one is created with empty contact fields
// (tolerance to out-of-order events).
func applyEmpleadoActualizado(ctx context.Context, tx *sql.Tx, d domain.EventData) error {
	if _, err := tx.ExecContext(ctx, `
INSERT INTO perfiles (empleado_id, nombre, apellido, email)
VALUES ($1, $2, $3, $4)
ON CONFLICT (empleado_id) DO UPDATE
SET nombre = EXCLUDED.nombre,
    apellido = EXCLUDED.apellido,
    email = EXCLUDED.email,
    fecha_actualizacion = now()
WHERE perfiles.archivado = FALSE
`, d.ID, d.Nombre, d.Apellido, d.Email); err != nil {
		return fmt.Errorf("apply empleado.actualizado: %w", err)
	}
	return nil
}

// applyEmpleadoRetirado sets archivado = TRUE (never deletes). If no profile
// exists it creates an archived one directly.
func applyEmpleadoRetirado(ctx context.Context, tx *sql.Tx, d domain.EventData) error {
	if _, err := tx.ExecContext(ctx, `
INSERT INTO perfiles (empleado_id, nombre, apellido, email, archivado)
VALUES ($1, $2, $3, $4, TRUE)
ON CONFLICT (empleado_id) DO UPDATE
SET archivado = TRUE,
    fecha_actualizacion = now()
`, d.ID, d.Nombre, d.Apellido, d.Email); err != nil {
		return fmt.Errorf("apply empleado.retirado: %w", err)
	}
	return nil
}

const profileColumns = `
id, empleado_id, nombre, apellido, email,
telefono, direccion, ciudad, biografia,
archivado, fecha_creacion, fecha_actualizacion
`

func scanProfile(row interface{ Scan(...any) error }) (domain.Profile, error) {
	var p domain.Profile
	err := row.Scan(
		&p.ID, &p.EmpleadoID, &p.Nombre, &p.Apellido, &p.Email,
		&p.Telefono, &p.Direccion, &p.Ciudad, &p.Biografia,
		&p.Archivado, &p.FechaCreacion, &p.FechaActualizacion,
	)
	return p, err
}

// List returns all profiles ordered by creation date.
func (s *Store) List(ctx context.Context) ([]domain.Profile, error) {
	rows, err := s.db.QueryContext(ctx,
		`SELECT `+profileColumns+` FROM perfiles ORDER BY fecha_creacion, id`)
	if err != nil {
		return nil, fmt.Errorf("list perfiles: %w", err)
	}
	defer rows.Close()

	perfiles := []domain.Profile{}
	for rows.Next() {
		p, err := scanProfile(rows)
		if err != nil {
			return nil, fmt.Errorf("scan perfil: %w", err)
		}
		perfiles = append(perfiles, p)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate perfiles: %w", err)
	}
	return perfiles, nil
}

// GetByEmpleadoID returns the profile for the given empleadoId.
func (s *Store) GetByEmpleadoID(ctx context.Context, empleadoID string) (domain.Profile, error) {
	p, err := scanProfile(s.db.QueryRowContext(ctx,
		`SELECT `+profileColumns+` FROM perfiles WHERE empleado_id = $1`, empleadoID))
	if err == sql.ErrNoRows {
		return domain.Profile{}, store.ErrNotFound
	}
	if err != nil {
		return domain.Profile{}, fmt.Errorf("get perfil: %w", err)
	}
	return p, nil
}

// UpdateContactInfo applies a partial update of telefono, direccion, ciudad
// and biografia (nil keeps the current value). Identity fields are never
// touched. Returns ErrNotFound when the profile does not exist.
func (s *Store) UpdateContactInfo(
	ctx context.Context, empleadoID string, u domain.ProfileUpdate,
) (domain.Profile, error) {
	p, err := scanProfile(s.db.QueryRowContext(ctx, `
UPDATE perfiles SET
	telefono  = COALESCE($2, telefono),
	direccion = COALESCE($3, direccion),
	ciudad    = COALESCE($4, ciudad),
	biografia = COALESCE($5, biografia),
	fecha_actualizacion = now()
WHERE empleado_id = $1
RETURNING `+profileColumns,
		empleadoID, u.Telefono, u.Direccion, u.Ciudad, u.Biografia))
	if err == sql.ErrNoRows {
		return domain.Profile{}, store.ErrNotFound
	}
	if err != nil {
		return domain.Profile{}, fmt.Errorf("update perfil: %w", err)
	}
	return p, nil
}
