// Package store defines the persistence port of perfiles-service.
// The AMQP consumer and the REST handlers depend on this interface, not on
// a concrete driver, so unit tests run without Postgres.
package store

import (
	"context"
	"errors"

	"perfiles-service/internal/domain"
)

// ErrNotFound is returned when no profile exists for the given empleadoId.
var ErrNotFound = errors.New("profile not found")

// Store is the persistence port. Implementations must be safe for one
// consumer goroutine plus the REST HTTP handlers.
type Store interface {
	// EnsureSchema creates the tables if they do not exist (single-way
	// migration, see init.sql).
	EnsureSchema(ctx context.Context) error

	Close() error

	// ApplyEvent atomically applies one ecosystem event:
	// effect + dedup mark (eventos_procesados) in the same transaction.
	//
	// Returns applied=false when the event id was already processed
	// (duplicate → no effect) or the type is unknown (ignored).
	// The consumer ACKs in both cases; on error it NACKs with requeue.
	ApplyEvent(ctx context.Context, ev domain.Event) (applied bool, err error)

	// List returns all profiles ordered by fechaCreacion.
	List(ctx context.Context) ([]domain.Profile, error)

	// GetByEmpleadoID returns the profile for the given empleadoId, or
	// ErrNotFound.
	GetByEmpleadoID(ctx context.Context, empleadoID string) (domain.Profile, error)

	// UpdateContactInfo applies a partial update of telefono, direccion,
	// ciudad and biografia (nil keeps the current value; identity fields
	// are never touched). Returns ErrNotFound if the profile does not exist.
	UpdateContactInfo(ctx context.Context, empleadoID string, u domain.ProfileUpdate) (domain.Profile, error)
}
