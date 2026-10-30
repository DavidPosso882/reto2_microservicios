// Package consumer implements the AMQP consumer of perfiles-service.
//
// Contract (CATALOGO_EVENTOS.md section 2):
//   - durable queue q.perfiles bound to durable topic exchange
//     ecosistema.eventos with routing keys empleado.creado,
//     empleado.actualizado, empleado.retirado
//   - manual ACK AFTER persisting the effect
//   - deduplication by event id (eventos_procesados): repeated id → ACK
//     without effect
//   - retry with backoff while the broker is unavailable
package consumer

import (
	"context"
	"fmt"
	"log/slog"
	"sync/atomic"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"

	"perfiles-service/internal/observability"
	"perfiles-service/internal/store"
)

const (
	Exchange   = "ecosistema.eventos"
	QueueName  = "q.perfiles"
	WorkerName = "perfiles-service"

	retryBaseDelay = 2 * time.Second
	retryMaxDelay  = 30 * time.Second
)

var routingKeys = []string{
	"empleado.creado",
	"empleado.actualizado",
	"empleado.retirado",
}

// Consumer consumes ecosystem events and applies them through the store.
type Consumer struct {
	URL    string
	Store  store.Store
	Logger *slog.Logger

	connected atomic.Bool
}

// BrokerStatus reports real AMQP connectivity for /health.
func (c *Consumer) BrokerStatus() string {
	if c.connected.Load() {
		return "UP"
	}
	return "DOWN"
}

func (c *Consumer) logger() *slog.Logger {
	if c.Logger != nil {
		return c.Logger
	}
	return observability.NewLogger("perfiles-service")
}

// Run blocks consuming events until ctx is cancelled. Every connection or
// consume failure is retried with exponential backoff (2s → 30s cap), so a
// broker that is not ready at startup does not kill the service.
func (c *Consumer) Run(ctx context.Context) error {
	delay := retryBaseDelay
	for {
		err := c.consumeOnce(ctx)
		if ctx.Err() != nil {
			return nil
		}
		if err == nil {
			err = fmt.Errorf("consume loop exited unexpectedly")
		}
		c.logger().Warn("perfiles-consumer: retrying", slog.String("error", err.Error()), slog.Duration("delay", delay))
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(delay):
		}
		delay *= 2
		if delay > retryMaxDelay {
			delay = retryMaxDelay
		}
	}
}

func (c *Consumer) consumeOnce(ctx context.Context) error {
	conn, err := amqp.Dial(c.URL)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()
	c.connected.Store(true)
	defer c.connected.Store(false)

	ch, err := conn.Channel()
	if err != nil {
		return fmt.Errorf("channel: %w", err)
	}
	defer ch.Close()

	if err := ch.Qos(1, 0, false); err != nil {
		return fmt.Errorf("qos: %w", err)
	}

	if _, err := ch.QueueDeclare(QueueName, true, false, false, false, nil); err != nil {
		return fmt.Errorf("declare queue: %w", err)
	}
	for _, key := range routingKeys {
		if err := ch.QueueBind(QueueName, key, Exchange, false, nil); err != nil {
			return fmt.Errorf("bind %s: %w", key, err)
		}
	}

	deliveries, err := ch.Consume(QueueName, WorkerName, false, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("consume: %w", err)
	}

	c.logger().Info("perfiles-consumer: consuming",
		slog.String("queue", QueueName),
		slog.String("exchange", Exchange),
	)
	for {
		select {
		case <-ctx.Done():
			return nil
		case d, ok := <-deliveries:
			if !ok {
				return fmt.Errorf("delivery channel closed")
			}
			c.Handle(ctx, d)
		}
	}
}
