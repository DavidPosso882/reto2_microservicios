// handle() of the consumer: decode → atomic apply (effect + dedup) → ACK.
package consumer

import (
	"context"
	"encoding/json"
	"log"

	amqp "github.com/rabbitmq/amqp091-go"

	"perfiles-service/internal/domain"
)

// Handle processes one delivery (exported for tests).
//
// The store applies the effect and the dedup mark in one transaction; the
// manual ACK happens only after that transaction committed. If anything
// fails before the ACK, the message is NACKed with requeue so the broker
// redelivers it (dedup makes reprocessing safe).
func (c *Consumer) Handle(ctx context.Context, d amqp.Delivery) {
	var ev domain.Event
	if err := json.Unmarshal(d.Body, &ev); err != nil {
		// Malformed message: ACK to discard (poison-pill guard).
		log.Printf("perfiles-consumer: malformed message: %v; ACKing to discard", err)
		_ = d.Ack(false)
		return
	}

	applied, err := c.Store.ApplyEvent(ctx, ev)
	if err != nil {
		log.Printf("perfiles-consumer: apply failed (id=%s type=%s): %v; NACK requeue", ev.ID, ev.Type, err)
		_ = d.Nack(false, true)
		return
	}
	if !applied {
		// Duplicate id or unknown type → ACK without effect.
		log.Printf("perfiles-consumer: no-op event (id=%s type=%s) → ACK without effect", ev.ID, ev.Type)
	}
	_ = d.Ack(false)
}
