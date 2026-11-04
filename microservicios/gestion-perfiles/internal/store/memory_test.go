// Tests of the in-memory store: event semantics + dedup + REST-facing ops.
// These run without Postgres; the Postgres implementation shares the same
// contract and is exercised by the Docker verification flow (README).
package store_test

import (
	"context"
	"testing"
	"time"

	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

func creado(id string, data domain.EventData) domain.Event {
	return domain.Event{
		ID: id, Type: "empleado.creado", Version: "1.0",
		OccurredAt: "2026-09-21T14:30:00Z", Producer: "empleados-service",
		Data: data,
	}
}

func empleadoFoto(id, nombre, apellido, email string) domain.EventData {
	return domain.EventData{ID: id, Nombre: nombre, Apellido: apellido, Email: email}
}

// TestCreadoCreaPerfilPorDefecto: empleado.creado → default profile with
// empty contact fields.
func TestCreadoCreaPerfilPorDefecto(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	applied, err := s.ApplyEvent(ctx, creado("ev-1", empleadoFoto("E001", "Juan", "Pérez", "juan.perez@empresa.com")))
	if err != nil || !applied {
		t.Fatalf("apply: applied=%v err=%v", applied, err)
	}

	p, err := s.GetByEmpleadoID(ctx, "E001")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if p.Nombre != "Juan" || p.Apellido != "Pérez" || p.Email != "juan.perez@empresa.com" {
		t.Errorf("identity fields not copied: %+v", p)
	}
	if p.Telefono != "" || p.Direccion != "" || p.Ciudad != "" || p.Biografia != "" {
		t.Errorf("default profile must have empty contact fields: %+v", p)
	}
	if p.Archivado {
		t.Errorf("new profile must not be archived")
	}
	if p.ID == "" || p.EmpleadoID != "E001" || p.FechaCreacion.IsZero() {
		t.Errorf("missing id/empleadoId/fechaCreacion: %+v", p)
	}
}

// TestCreadoDuplicadoNoDuplica: same event id → second call is a no-op.
func TestCreadoDuplicadoNoDuplica(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	ev := creado("ev-1", empleadoFoto("E001", "Juan", "Pérez", "juan.perez@empresa.com"))
	if _, err := s.ApplyEvent(ctx, ev); err != nil {
		t.Fatalf("first apply: %v", err)
	}
	applied, err := s.ApplyEvent(ctx, ev)
	if err != nil {
		t.Fatalf("second apply: %v", err)
	}
	if applied {
		t.Errorf("duplicate event id must report applied=false")
	}

	list, err := s.List(ctx)
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if len(list) != 1 {
		t.Errorf("expected exactly 1 profile, got %d", len(list))
	}
}

// TestActualizadoSincronizaSinPisar: empleado.actualizado syncs ONLY
// nombre/apellido/email; contact fields are preserved.
func TestActualizadoSincronizaSinPisar(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	if _, err := s.ApplyEvent(ctx, creado("ev-1", empleadoFoto("E001", "Juan", "Pérez", "viejo@empresa.com"))); err != nil {
		t.Fatalf("creado: %v", err)
	}

	telefono, biografia := "+54 11 4444-5555", "Perfil del empleado"
	if _, err := s.UpdateContactInfo(ctx, "E001", domain.ProfileUpdate{Telefono: &telefono, Biografia: &biografia}); err != nil {
		t.Fatalf("update contact: %v", err)
	}

	before, _ := s.GetByEmpleadoID(ctx, "E001")
	time.Sleep(1 * time.Millisecond) // ensure fechaActualizacion moves

	if _, err := s.ApplyEvent(ctx, domain.Event{
		ID: "ev-2", Type: "empleado.actualizado", Version: "1.0",
		Producer: "empleados-service", Data: empleadoFoto("E001", "Juan Carlos", "Pérez Gómez", "nuevo@empresa.com"),
	}); err != nil {
		t.Fatalf("actualizado: %v", err)
	}

	p, err := s.GetByEmpleadoID(ctx, "E001")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if p.Nombre != "Juan Carlos" || p.Apellido != "Pérez Gómez" || p.Email != "nuevo@empresa.com" {
		t.Errorf("identity fields were not synchronized: %+v", p)
	}
	if p.Telefono != telefono || p.Biografia != biografia {
		t.Errorf("contact fields were overwritten: %+v", p)
	}
	if !p.FechaActualizacion.After(before.FechaActualizacion) {
		t.Errorf("fechaActualizacion did not move: %v -> %v", before.FechaActualizacion, p.FechaActualizacion)
	}
}

// TestActualizadoCreaSiNoExiste: order tolerance — no profile yet → create.
func TestActualizadoCreaSiNoExiste(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	if _, err := s.ApplyEvent(ctx, domain.Event{
		ID: "ev-1", Type: "empleado.actualizado", Version: "1.0",
		Producer: "empleados-service", Data: empleadoFoto("E002", "Ana", "López", "ana.lopez@empresa.com"),
	}); err != nil {
		t.Fatalf("actualizado: %v", err)
	}

	p, err := s.GetByEmpleadoID(ctx, "E002")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if p.Nombre != "Ana" || p.Email != "ana.lopez@empresa.com" || p.Telefono != "" || p.Archivado {
		t.Errorf("unexpected created profile: %+v", p)
	}
}

// TestRetiradoArchivaSinBorrar: empleado.retirado → archivado=true, data kept.
func TestRetiradoArchivaSinBorrar(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	if _, err := s.ApplyEvent(ctx, creado("ev-1", empleadoFoto("E001", "Juan", "Pérez", "juan.perez@empresa.com"))); err != nil {
		t.Fatalf("creado: %v", err)
	}
	telefono := "123"
	if _, err := s.UpdateContactInfo(ctx, "E001", domain.ProfileUpdate{Telefono: &telefono}); err != nil {
		t.Fatalf("update: %v", err)
	}

	if _, err := s.ApplyEvent(ctx, domain.Event{
		ID: "ev-2", Type: "empleado.retirado", Version: "1.0",
		Producer: "empleados-service", Data: empleadoFoto("E001", "Juan", "Pérez", "juan.perez@empresa.com"),
	}); err != nil {
		t.Fatalf("retirado: %v", err)
	}

	p, err := s.GetByEmpleadoID(ctx, "E001")
	if err != nil {
		t.Fatalf("perfil was deleted: %v", err)
	}
	if !p.Archivado {
		t.Errorf("profile must be archived, not deleted")
	}
	if p.Telefono != telefono {
		t.Errorf("contact info must be preserved: %+v", p)
	}

	// Sync after retirement must NOT unarchive it.
	if _, err := s.ApplyEvent(ctx, domain.Event{
		ID: "ev-3", Type: "empleado.actualizado", Version: "1.0",
		Producer: "empleados-service", Data: empleadoFoto("E001", "Otro", "Nombre", "otro@empresa.com"),
	}); err != nil {
		t.Fatalf("actualizado post-retiro: %v", err)
	}
	p, _ = s.GetByEmpleadoID(ctx, "E001")
	if !p.Archivado || p.Nombre != "Juan" {
		t.Errorf("actualizado must not touch archived profiles: %+v", p)
	}
}

// TestRetiradoSinPerfilCreaArchivado: order tolerance for empleado.retirado.
func TestRetiradoSinPerfilCreaArchivado(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	if _, err := s.ApplyEvent(ctx, domain.Event{
		ID: "ev-1", Type: "empleado.retirado", Version: "1.0",
		Producer: "empleados-service", Data: empleadoFoto("E003", "Luis", "García", "luis.garcia@empresa.com"),
	}); err != nil {
		t.Fatalf("retirado: %v", err)
	}

	p, err := s.GetByEmpleadoID(ctx, "E003")
	if err != nil {
		t.Fatalf("get: %v", err)
	}
	if !p.Archivado || p.Nombre != "Luis" || p.Email != "luis.garcia@empresa.com" {
		t.Errorf("expected archived profile created directly: %+v", p)
	}
}

// TestUpdateContactInfoIgnoraIdentidad: PUT can never change identity fields.
func TestUpdateContactInfoIgnoraIdentidad(t *testing.T) {
	s := store.NewMemoryStore()
	ctx := context.Background()

	if _, err := s.ApplyEvent(ctx, creado("ev-1", empleadoFoto("E001", "Juan", "Pérez", "juan.perez@empresa.com"))); err != nil {
		t.Fatalf("creado: %v", err)
	}

	nombre := "Hacker"
	direccion := "Calle Falsa 123"
	// The API-level ProfileUpdate struct has no identity fields at all; this
	// proves identity can only change through events.
	if _, err := s.UpdateContactInfo(ctx, "E001", domain.ProfileUpdate{Direccion: &direccion}); err != nil {
		t.Fatalf("update: %v", err)
	}
	_ = nombre // nombre is not part of ProfileUpdate by design

	p, _ := s.GetByEmpleadoID(ctx, "E001")
	if p.Nombre != "Juan" || p.Email != "juan.perez@empresa.com" {
		t.Errorf("identity changed through UpdateContactInfo: %+v", p)
	}
	if p.Direccion != direccion {
		t.Errorf("direccion not updated: %+v", p)
	}
}

// TestUpdateContactInfoNoEncontrado: 404 path of the REST API.
func TestUpdateContactInfoNoEncontrado(t *testing.T) {
	s := store.NewMemoryStore()
	ciudad := "Córdoba"
	_, err := s.UpdateContactInfo(context.Background(), "NOPE", domain.ProfileUpdate{Ciudad: &ciudad})
	if err != store.ErrNotFound {
		t.Errorf("expected ErrNotFound, got %v", err)
	}
}

// TestListInicialVacio: GET /perfiles over an empty store returns an empty
// (non-nil) array.
func TestListInicialVacio(t *testing.T) {
	s := store.NewMemoryStore()
	list, err := s.List(context.Background())
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	if list == nil || len(list) != 0 {
		t.Errorf("expected empty non-nil slice, got %#v", list)
	}
	_ = time.Now
}
