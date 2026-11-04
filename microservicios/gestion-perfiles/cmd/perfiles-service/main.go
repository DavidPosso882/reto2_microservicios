// Command perfiles-service: hybrid service of the ecosystem.
//
// It CONSUMES empleado.* events (RabbitMQ) to create/synchronize/archive
// profiles, and EXPOSES a REST API to query and update profile contact info.
package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"perfiles-service/internal/api"
	"perfiles-service/internal/config"
	"perfiles-service/internal/consumer"
	"perfiles-service/internal/observability"
	"perfiles-service/internal/store/postgres"
)

func main() {
	cfg := config.Load()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	logger := observability.NewLogger("perfiles-service")

	// ── OpenTelemetry (Reto 8) ──────────────────────────────────────────
	shutdownTracing, err := observability.InitTracing(ctx, "perfiles-service")
	if err != nil {
		logger.Warn("perfiles-service: tracing disabled", slog.String("error", err.Error()))
	}
	defer observability.ShutdownWithTimeout(shutdownTracing, 5*time.Second)

	metrics := observability.NewMetrics("perfiles-service")

	// ── Store (Postgres) ────────────────────────────────────────────────
	st, err := postgres.New(cfg.PostgresDSN())
	if err != nil {
		logger.Error("perfiles-service: postgres", slog.String("error", err.Error()))
		os.Exit(1)
	}
	defer st.Close()

	// Retry the DB connection while Postgres starts up.
	for i := 0; ; i++ {
		err := st.EnsureSchema(ctx)
		if err == nil {
			break
		}
		if i >= 15 {
			logger.Error("perfiles-service: schema not ready", slog.String("error", err.Error()))
			os.Exit(1)
		}
		logger.Warn("perfiles-service: waiting for postgres",
			slog.Int("attempt", i+1), slog.String("error", err.Error()))
		select {
		case <-ctx.Done():
			logger.Error("perfiles-service: cancelled while waiting for postgres")
			os.Exit(1)
		case <-time.After(2 * time.Second):
		}
	}
	logger.Info("perfiles-service: schema ready")

	// ── REST API ────────────────────────────────────────────────────────
	openapiYAML, err := os.ReadFile("openapi.yaml")
	if err != nil {
		logger.Error("perfiles-service: read openapi.yaml", slog.String("error", err.Error()))
		os.Exit(1)
	}

	// The consumer is created before the HTTP server so /health can report
	// the real AMQP connection state.
	cons := &consumer.Consumer{URL: cfg.RabbitMQURL, Store: st, Logger: logger}
	server := &api.Server{
		Store:        st,
		HealthCheck:  st.Ping,
		BrokerStatus: cons.BrokerStatus,
		Metrics:      metrics,
		Logger:       logger,
	}

	httpServer := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           server.Handler(openapiYAML),
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		logger.Info("perfiles-service: REST API listening", slog.String("port", cfg.Port))
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("perfiles-service: http server", slog.String("error", err.Error()))
			os.Exit(1)
		}
	}()

	// ── AMQP consumer (background, retries with backoff) ───────────────
	logger.Info("perfiles-service: starting consumer")
	go func() {
		if err := cons.Run(ctx); err != nil {
			logger.Error("perfiles-service: consumer stopped", slog.String("error", err.Error()))
		}
	}()

	// Block until SIGINT/SIGTERM, then shut down gracefully.
	<-ctx.Done()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		logger.Warn("perfiles-service: http shutdown", slog.String("error", err.Error()))
	}
	logger.Info("perfiles-service: stopped")
}
