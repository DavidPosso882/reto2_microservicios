// Consumer-level tests: decode + dedup + ACK/NACK behaviour using the
// in-memory store and a fake AMQP Acknowledger (no RabbitMQ needed).
package consumer_test

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	amqp "github.com/rabbitmq/amqp091-go"

	"perfiles-service/internal/consumer"
	"perfiles-service/internal/domain"
	"perfiles-service/internal/store"
)

// fakeAcknowledger records Ack/Nack calls, like the real amqp channel would.
type fakeAcknowledger struct {
	acks    int
	nacks   int
	requeue bool
}

func (f *fakeAcknowledger) Ack(tag uint64, multiple bool) error { f.acks++; return nil }
func (f *fakeAcknowledger) Nack(tag uint64, multiple bool, requeue bool) error {
	f.nacks++
	f.requeue = requeue
	return nil
}
func (f *fakeAcknowledger) Reject(tag uint64, requeue bool) error { return nil }

func delivery(body string, ack *fakeAcknowledger) amqp.Delivery {
	return amqp.Delivery{Body: []byte(body), Acknowledger: ack}
}

func envelope(id, evType string, data domain.EventData) string {
	ev := domain.Event{
		ID: id, Type: evType, Version: "1.0",
		OccurredAt: "2026-09-21T14:30:00Z", Producer: "empleados-service",
		Data: data,
	}
	raw, _ := json.Marshal(ev)
	return string(raw)
}

// TestHandleAplicaYAck: valid event → effect applied → manual ACK after
// persisting.
func TestHandleAplicaYAck(t *testing.T) {
	s := store.NewMemoryStore()
	c := &consumer.Consumer{Store: s}
	ack := &fakeAcknowledger{}

	body := envelope("ev-1", "empleado.creado", domain.EventData{ID: "E001", Nombre: "Juan", Apellido: "Pérez", Email: "juan.perez@empresa.com"})
	c.Handle(context.Background(), delivery(body, ack))

	if ack.acks != 1 || ack.nacks != 0 {
		t.Errorf("expected 1 ack / 0 nack, got acks=%d nacks=%d", ack.acks, ack.nacks)
	}
	p, err := s.GetByEmpleadoID(context.Background(), "E001")
	if err != nil || p.Nombre != "Juan" {
		t.Fatalf("effect not applied: %+v err=%v", p, err)
	}
	if p.Telefono != "" {
		t.Errorf("default profile must have empty contact fields: %+v", p)
	}
}

// TestHandleDuplicadoAckSinEfecto: repeated id → ACK without any effect.
func TestHandleDuplicadoAckSinEfecto(t *testing.T) {
	s := store.NewMemoryStore()
	c := &consumer.Consumer{Store: s}
	ctx := context.Background()

	body := envelope("ev-1", "empleado.creado", domain.EventData{ID: "E001", Nombre: "Juan", Apellido: "Pérez", Email: "juan.perez@empresa.com"})
	c.Handle(ctx, delivery(body, &fakeAcknowledger{}))

	// Tamper with the profile: a duplicate id must not rewrite it.
	s.SeedForTests(domain.Profile{EmpleadoID: "E001", Nombre: "MODIFICADO"})
	ack := &fakeAcknowledger{}
	c.Handle(ctx, delivery(body, ack))

	if ack.acks != 1 || ack.nacks != 0 {
		t.Errorf("duplicate must be ACKed without effect: acks=%d nacks=%d", ack.acks, ack.nacks)
	}
	p, _ := s.GetByEmpleadoID(ctx, "E001")
	if p.Nombre != "MODIFICADO" {
		t.Errorf("duplicate event must have no effect, got: %+v", p)
	}
}

// TestHandleMalformadoAck: malformed JSON → ACK (poison pill discarded).
func TestHandleMalformadoAck(t *testing.T) {
	s := store.NewMemoryStore()
	c := &consumer.Consumer{Store: s}
	ack := &fakeAcknowledger{}

	c.Handle(context.Background(), delivery("{no-json", ack))
	if ack.acks != 1 || ack.nacks != 0 {
		t.Errorf("malformed message must be ACKed and discarded: acks=%d nacks=%d", ack.acks, ack.nacks)
	}
}

// TestHandleTipoDesconocidoAck: unknown event type → ACK, no effect, no crash.
func TestHandleTipoDesconocidoAck(t *testing.T) {
	s := store.NewMemoryStore()
	c := &consumer.Consumer{Store: s}
	ack := &fakeAcknowledger{}

	body := envelope("ev-9", "vacaciones.programadas", domain.EventData{ID: "V-1"})
	c.Handle(context.Background(), delivery(body, ack))
	if ack.acks != 1 || ack.nacks != 0 {
		t.Errorf("unknown type must be ACKed: acks=%d nacks=%d", ack.acks, ack.nacks)
	}
}

// failingStore wraps MemoryStore but fails on ApplyEvent to force NACK.
type failingStore struct {
	store.Store
	fail bool
}

func (f *failingStore) ApplyEvent(ctx context.Context, ev domain.Event) (bool, error) {
	if f.fail {
		return false, errors.New("db down")
	}
	return f.Store.ApplyEvent(ctx, ev)
}

// TestHandleErrorNackRequeue: store failure → NACK with requeue (no ACK).
func TestHandleErrorNackRequeue(t *testing.T) {
	s := &failingStore{Store: store.NewMemoryStore(), fail: true}
	c := &consumer.Consumer{Store: s}
	ack := &fakeAcknowledger{}

	body := envelope("ev-1", "empleado.creado", domain.EventData{ID: "E001", Nombre: "Juan", Apellido: "Pérez", Email: "juan.perez@empresa.com"})
	c.Handle(context.Background(), delivery(body, ack))

	if ack.nacks != 1 || !ack.requeue || ack.acks != 0 {
		t.Errorf("expected 1 nack with requeue and no ack, got acks=%d nacks=%d requeue=%v", ack.acks, ack.nacks, ack.requeue)
	}
}
