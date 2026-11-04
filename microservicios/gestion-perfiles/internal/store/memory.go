// Package store: in-memory implementation of Store, used by unit tests
// (and handy for local experiments). It replicates the same semantics as
// the Postgres implementation: atomic event application with dedup, safe
// upserts and archive-only retirement.
package store

import (
	"context"
	"fmt"
	"sync"
	"time"

	"perfiles-service/internal/domain"
)

// MemoryStore is a thread-safe Store backed by plain maps.
type MemoryStore struct {
	mu         sync.Mutex
	byEmpleado map[string]domain.Profile
	procesados map[string]bool
	created    []string // empleadoIds in creation order
	counter    int
	now        func() time.Time
}

// NewMemoryStore builds an empty in-memory store.
func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		byEmpleado: map[string]domain.Profile{},
		procesados: map[string]bool{},
		now:        time.Now,
	}
}

// EnsureSchema is a no-op for the memory store.
func (m *MemoryStore) EnsureSchema(context.Context) error { return nil }

// Close is a no-op for the memory store.
func (m *MemoryStore) Close() error { return nil }

// ClockForTests overrides the clock used for timestamps (test helper).
func (m *MemoryStore) ClockForTests(now func() time.Time) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.now = now
}

// ApplyEvent mirrors the Postgres semantics: effect + dedup mark, applied
// =false for duplicate ids and unknown types.
func (m *MemoryStore) ApplyEvent(_ context.Context, ev domain.Event) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.procesados[ev.ID] {
		return false, nil // duplicate → no effect
	}

	now := m.now()
	switch ev.Type {
	case "empleado.creado":
		if p, ok := m.byEmpleado[ev.Data.ID]; ok {
			p.Nombre, p.Apellido, p.Email = ev.Data.Nombre, ev.Data.Apellido, ev.Data.Email
			p.FechaActualizacion = now
			m.byEmpleado[p.EmpleadoID] = p
		} else {
			m.create(ev.Data.ID, ev.Data.Nombre, ev.Data.Apellido, ev.Data.Email, false, now)
		}
	case "empleado.actualizado":
		if p, ok := m.byEmpleado[ev.Data.ID]; ok {
			if !p.Archivado {
				p.Nombre, p.Apellido, p.Email = ev.Data.Nombre, ev.Data.Apellido, ev.Data.Email
				p.FechaActualizacion = now
				m.byEmpleado[p.EmpleadoID] = p
			}
		} else {
			m.create(ev.Data.ID, ev.Data.Nombre, ev.Data.Apellido, ev.Data.Email, false, now)
		}
	case "empleado.retirado":
		if p, ok := m.byEmpleado[ev.Data.ID]; ok {
			p.Archivado = true
			p.FechaActualizacion = now
			m.byEmpleado[p.EmpleadoID] = p
		} else {
			m.create(ev.Data.ID, ev.Data.Nombre, ev.Data.Apellido, ev.Data.Email, true, now)
		}
	default:
		// Unknown type: mark processed, no effect.
	}

	m.procesados[ev.ID] = true
	return true, nil
}

func (m *MemoryStore) create(empleadoID, nombre, apellido, email string, archivado bool, now time.Time) {
	m.counter++
	m.byEmpleado[empleadoID] = domain.Profile{
		ID:                 fmt.Sprintf("00000000-0000-0000-0000-%012d", m.counter),
		EmpleadoID:         empleadoID,
		Nombre:             nombre,
		Apellido:           apellido,
		Email:              email,
		Archivado:          archivado,
		FechaCreacion:      now,
		FechaActualizacion: now,
	}
	m.created = append(m.created, empleadoID)
}

// List returns all profiles in creation order.
func (m *MemoryStore) List(_ context.Context) ([]domain.Profile, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := []domain.Profile{}
	for _, id := range m.created {
		out = append(out, m.byEmpleado[id])
	}
	return out, nil
}

// GetByEmpleadoID returns the profile or ErrNotFound.
func (m *MemoryStore) GetByEmpleadoID(_ context.Context, empleadoID string) (domain.Profile, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	p, ok := m.byEmpleado[empleadoID]
	if !ok {
		return domain.Profile{}, ErrNotFound
	}
	return p, nil
}

// UpdateContactInfo partially updates contact fields; identity fields are
// never touched. Returns ErrNotFound when absent.
func (m *MemoryStore) UpdateContactInfo(
	_ context.Context, empleadoID string, u domain.ProfileUpdate,
) (domain.Profile, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	p, ok := m.byEmpleado[empleadoID]
	if !ok {
		return domain.Profile{}, ErrNotFound
	}
	if u.Telefono != nil {
		p.Telefono = *u.Telefono
	}
	if u.Direccion != nil {
		p.Direccion = *u.Direccion
	}
	if u.Ciudad != nil {
		p.Ciudad = *u.Ciudad
	}
	if u.Biografia != nil {
		p.Biografia = *u.Biografia
	}
	p.FechaActualizacion = m.now()
	m.byEmpleado[empleadoID] = p
	return p, nil
}

// SeedForTests inserts a profile directly, bypassing the event pipeline
// (REST test helper).
func (m *MemoryStore) SeedForTests(p domain.Profile) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, ok := m.byEmpleado[p.EmpleadoID]; !ok {
		m.created = append(m.created, p.EmpleadoID)
	}
	m.byEmpleado[p.EmpleadoID] = p
}
