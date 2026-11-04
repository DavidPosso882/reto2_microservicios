package observability

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"time"

	"go.opentelemetry.io/otel/trace"
)

// NewLogger returns a JSON logger whose top-level keys match the Reto 8
// contract: timestamp, level, service, traceId, message (+ structured fields).
func NewLogger(service string) *slog.Logger {
	if configured := os.Getenv("OTEL_SERVICE_NAME"); configured != "" {
		service = configured
	}
	handler := slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
		ReplaceAttr: func(groups []string, attr slog.Attr) slog.Attr {
			if len(groups) != 0 {
				return attr
			}
			switch attr.Key {
			case slog.TimeKey:
				attr.Key = "timestamp"
			case slog.LevelKey:
				attr.Key = "level"
			case slog.MessageKey:
				attr.Key = "message"
			}
			return attr
		},
	})
	return slog.New(handler).With(slog.String("service", service))
}

// RequestLogger emits one JSON line per HTTP request with the active trace id.
func RequestLogger(logger *slog.Logger, next http.Handler) http.Handler {
	if logger == nil {
		logger = slog.Default()
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		recorder := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(recorder, r)

		logger.InfoContext(r.Context(), "http_request",
			slog.String("traceId", TraceID(r.Context())),
			slog.String("method", r.Method),
			slog.String("path", r.URL.Path),
			slog.Int("status", recorder.status),
			slog.Int64("duration_ms", time.Since(started).Milliseconds()),
		)
	})
}

// TraceID returns the active 32-hex trace id or an empty string.
func TraceID(ctx context.Context) string {
	spanContext := trace.SpanContextFromContext(ctx)
	if !spanContext.IsValid() {
		return ""
	}
	return spanContext.TraceID().String()
}
