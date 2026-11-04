// Config tests: defaults, overrides and derived values (no I/O, env only).
package config_test

import (
	"strings"
	"testing"

	"perfiles-service/internal/config"
)

func TestLoadDefaults(t *testing.T) {
	cfg := config.Load()
	if cfg.Port != "8083" {
		t.Errorf("Port = %q, want 8083", cfg.Port)
	}
	if cfg.DBHost != "localhost" || cfg.DBPort != "5432" || cfg.DBName != "perfiles" {
		t.Errorf("DB defaults = %+v", cfg)
	}
	if !strings.HasPrefix(cfg.RabbitMQURL, "amqp://") {
		t.Errorf("RabbitMQURL = %q, want amqp://…", cfg.RabbitMQURL)
	}
}

func TestLoadOverrides(t *testing.T) {
	t.Setenv("PORT", "9999")
	t.Setenv("DB_HOST", "db-test")
	t.Setenv("DB_NAME", "perfiles_test")
	t.Setenv("RABBITMQ_URL", "amqp://u:p@host:5672/")

	cfg := config.Load()
	if cfg.Port != "9999" || cfg.DBHost != "db-test" || cfg.DBName != "perfiles_test" {
		t.Errorf("overrides not applied: %+v", cfg)
	}
	if cfg.RabbitMQURL != "amqp://u:p@host:5672/" {
		t.Errorf("RABBITMQ_URL must win, got %q", cfg.RabbitMQURL)
	}
}

func TestRabbitMQURLAssembledFromParts(t *testing.T) {
	t.Setenv("RABBITMQ_USER", "admin")
	t.Setenv("RABBITMQ_PASSWORD", "s3cret")
	t.Setenv("RABBITMQ_HOST", "broker")
	t.Setenv("RABBITMQ_PORT", "5673")

	cfg := config.Load()
	want := "amqp://admin:s3cret@broker:5673/"
	if cfg.RabbitMQURL != want {
		t.Errorf("RabbitMQURL = %q, want %q", cfg.RabbitMQURL, want)
	}
}

func TestPostgresDSNContainsParts(t *testing.T) {
	cfg := config.Load()
	dsn := cfg.PostgresDSN()
	for _, part := range []string{"host=", "port=", "user=", "dbname=", "sslmode=disable"} {
		if !strings.Contains(dsn, part) {
			t.Errorf("DSN %q missing %q", dsn, part)
		}
	}
}
