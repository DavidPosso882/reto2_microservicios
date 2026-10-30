// handle() of the consumer: decode → atomic apply (effect + dedup) → ACK.
package consumer

import (
	"context"
	"encoding/json"
	"log/slog"

	amqp "github.com/rabbitmq/amqp091-go"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"

	"perfiles-service/internal/domain"
	"perfiles-service/internal/observability"
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
		c.logger().WarnContext(ctx, "perfiles-consumer: malformed message; ACKing to discard",
			slog.String("error", err.Error()))
		_ = d.Ack(false)
		return
	}

	// Reto 8: continúa la traza distribuida desde las cabeceras AMQP
	// (traceparent/tracestate/baggage inyectados por el productor).
	ctx = otel.GetTextMapPropagator().Extract(ctx, amqpCarrier(d.Headers))
	ctx, span := otel.Tracer("perfiles-service").Start(ctx, "perfiles.consumir_evento")
	defer span.End()
	span.SetAttributes(
		attribute.String("event.id", ev.ID),
		attribute.String("event.type", ev.Type),
	)
	log := c.logger().With(slog.String("traceId", observability.TraceID(ctx)))

	applied, err := c.Store.ApplyEvent(ctx, ev)
	if err != nil {
		log.ErrorContext(ctx, "perfiles-consumer: apply failed; NACK requeue",
			slog.String("event.id", ev.ID), slog.String("event.type", ev.Type), slog.String("error", err.Error()))
		_ = d.Nack(false, true)
		return
	}
	if !applied {
		// Duplicate id or unknown type → ACK without effect.
		log.InfoContext(ctx, "perfiles-consumer: no-op event; ACK without effect",
			slog.String("event.id", ev.ID), slog.String("event.type", ev.Type))
	}
	_ = d.Ack(false)
}

// amqpCarrier adapts AMQP message headers to the OpenTelemetry TextMapCarrier
// interface so W3C propagation survives the broker hop.
type amqpCarrier amqp.Table

func (c amqpCarrier) Get(key string) string {
	value, ok := c[key]
	if !ok {
		return ""
	}
	text, _ := value.(string)
	return text
}

func (c amqpCarrier) Set(key, value string) {
	c[key] = value
}

func (c amqpCarrier) Keys() []string {
	keys := make([]string, 0, len(c))
	for key := range c {
		keys = append(keys, key)
	}
	return keys
}
