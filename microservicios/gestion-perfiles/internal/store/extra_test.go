// No-op and helper tests for the in-memory store (clock/seed/lifecycle).
package store_test

import (
	"context"
	"testing"
	"time"

	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

func TestEnsureSchemaAndCloseAreNoOps(t *testing.T) {
	s := store.NewMemoryStore()
	if err := s.EnsureSchema(context.Background()); err != nil {
		t.Errorf("EnsureSchema = %v, want nil", err)
	}
	if err := s.Close(); err != nil {
		t.Errorf("Close = %v, want nil", err)
	}
}

func TestClockForTestsControlsTimestamps(t *testing.T) {
	fixed := time.Date(2026, 11, 4, 12, 0, 0, 0, time.UTC)
	s := store.NewMemoryStore()
	s.ClockForTests(func() time.Time { return fixed })

	applied, err := s.ApplyEvent(context.Background(), domain.Event{
		ID:   "evt-1",
		Type: "empleado.creado",
		Data: domain.EventData{ID: "E100", Nombre: "Ada", Apellido: "Lovelace", Email: "ada@empresa.com"},
	})
	if err != nil || !applied {
		t.Fatalf("ApplyEvent = (%v, %v), want (true, nil)", applied, err)
	}
	got, err := s.GetByEmpleadoID(context.Background(), "E100")
	if err != nil {
		t.Fatalf("GetByEmpleadoID: %v", err)
	}
	if !got.FechaCreacion.Equal(fixed) {
		t.Errorf("FechaCreacion = %v, want %v", got.FechaCreacion, fixed)
	}
}

func TestSeedForTestsMakesProfileVisible(t *testing.T) {
	s := store.NewMemoryStore()
	s.SeedForTests(domain.Profile{EmpleadoID: "E200", Nombre: "Grace"})
	// Second seed of the same id keeps a single entry.
	s.SeedForTests(domain.Profile{EmpleadoID: "E200", Nombre: "Grace Hopper"})

	list, err := s.List(context.Background())
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(list) != 1 {
		t.Fatalf("List len = %d, want 1", len(list))
	}
	if _, err := s.GetByEmpleadoID(context.Background(), "E200"); err != nil {
		t.Errorf("GetByEmpleadoID: %v", err)
	}
}
