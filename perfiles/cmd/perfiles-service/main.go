// Command perfiles-service: hybrid service of the ecosystem.
//
// It CONSUMES empleado.* events (RabbitMQ) to create/synchronize/archive
// profiles, and EXPOSES a REST API to query and update profile contact info.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"perfiles-service/internal/api"
	"perfiles-service/internal/config"
	"perfiles-service/internal/consumer"
	"perfiles-service/internal/store/postgres"
)

func main() {
	cfg := config.Load()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// ── Store (Postgres) ────────────────────────────────────────────────
	st, err := postgres.New(cfg.PostgresDSN())
	if err != nil {
		log.Fatalf("perfiles-service: postgres: %v", err)
	}
	defer st.Close()

	// Retry the DB connection while Postgres starts up.
	for i := 0; ; i++ {
		err := st.EnsureSchema(ctx)
		if err == nil {
			break
		}
		if i >= 15 {
			log.Fatalf("perfiles-service: schema not ready: %v", err)
		}
		log.Printf("perfiles-service: waiting for postgres (%d): %v", i+1, err)
		select {
		case <-ctx.Done():
			log.Fatalf("perfiles-service: cancelled while waiting for postgres")
		case <-time.After(2 * time.Second):
		}
	}
	log.Printf("perfiles-service: schema ready")

	// ── REST API ────────────────────────────────────────────────────────
	openapiYAML, err := os.ReadFile("openapi.yaml")
	if err != nil {
		log.Fatalf("perfiles-service: read openapi.yaml: %v", err)
	}
	server := &api.Server{Store: st}

	httpServer := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           server.Handler(openapiYAML),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("perfiles-service: REST API listening on :%s", cfg.Port)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("perfiles-service: http server: %v", err)
		}
	}()

	// ── AMQP consumer (blocks, retries with backoff) ───────────────────
	log.Printf("perfiles-service: starting consumer (broker=%s)", cfg.RabbitMQURL)
	if err := (&consumer.Consumer{URL: cfg.RabbitMQURL, Store: st}).Run(ctx); err != nil {
		log.Printf("perfiles-service: consumer stopped: %v", err)
	}

	// ── Graceful shutdown of the HTTP server ───────────────────────────
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		log.Printf("perfiles-service: http shutdown: %v", err)
	}
	log.Printf("perfiles-service: stopped")
}
