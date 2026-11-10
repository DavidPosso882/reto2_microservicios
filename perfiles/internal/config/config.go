// Package config loads service configuration from environment variables
// with local-friendly defaults, following the same convention as the
// other services of the ecosystem.
package config

import (
	"fmt"
	"os"
	"strings"
)

// Config holds all runtime configuration for perfiles-service.
type Config struct {
	Port string

	DBHost     string
	DBPort     string
	DBName     string
	DBUser     string
	DBPassword string

	RabbitMQURL string
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// getsecret resolves a secret (Proyecto Final — cero secretos en el repo):
// KEY_FILE (Docker secret mounted at /run/secrets) wins over KEY; with
// neither it returns "" — never a hard-coded value. An unreadable file is
// reported as "" too, so the DB connection fails loudly at startup.
func getsecret(key string) string {
	if path := strings.TrimSpace(os.Getenv(key + "_FILE")); path != "" {
		b, err := os.ReadFile(path)
		if err != nil {
			return ""
		}
		return strings.TrimSpace(string(b))
	}
	return strings.TrimSpace(os.Getenv(key))
}

// Load reads configuration from the environment.
//
// RabbitMQ: RABBITMQ_URL wins when set; otherwise the URL is assembled
// from RABBITMQ_HOST / RABBITMQ_PORT / RABBITMQ_USER / RABBITMQ_PASSWORD.
func Load() Config {
	return Config{
		Port:       getenv("PORT", "8083"),
		DBHost:     getenv("DB_HOST", "localhost"),
		DBPort:     getenv("DB_PORT", "5432"),
		DBName:     getenv("DB_NAME", "perfiles"),
		DBUser:     getenv("DB_USER", "postgres"),
		DBPassword: getsecret("DB_PASSWORD"),

		RabbitMQURL: rabbitMQURL(),
	}
}

func rabbitMQURL() string {
	if u := os.Getenv("RABBITMQ_URL"); u != "" {
		return u
	}
	user := getenv("RABBITMQ_USER", "guest")
	pass := getenv("RABBITMQ_PASSWORD", "guest")
	host := getenv("RABBITMQ_HOST", "localhost")
	port := getenv("RABBITMQ_PORT", "5672")
	return fmt.Sprintf("amqp://%s:%s@%s:%s/", user, pass, host, port)
}

// PostgresDSN returns the lib/pq connection string.
func (c Config) PostgresDSN() string {
	return fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		c.DBHost, c.DBPort, c.DBUser, c.DBPassword, c.DBName,
	)
}
