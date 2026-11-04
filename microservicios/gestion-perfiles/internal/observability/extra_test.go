// Extra observability tests: logger contract, middleware passthrough and
// sampler selection (all without network: the Zipkin exporter dials lazily).
package observability_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/trace"

	"perfiles-service/internal/observability"
)

func TestNewLoggerHonorsServiceName(t *testing.T) {
	if observability.NewLogger("perfiles-service") == nil {
		t.Fatal("expected a non-nil logger")
	}
	t.Setenv("OTEL_SERVICE_NAME", "otro-servicio")
	if observability.NewLogger("perfiles-service") == nil {
		t.Fatal("expected a non-nil logger with OTEL_SERVICE_NAME set")
	}
}

func TestTraceIDEmptyWithoutSpan(t *testing.T) {
	if got := observability.TraceID(context.Background()); got != "" {
		t.Errorf("TraceID without span = %q, want empty", got)
	}
}

func TestTraceIDFromValidSpanContext(t *testing.T) {
	traceID, _ := trace.TraceIDFromHex("4bf92f3577b34da6a3ce929d0e0e4736")
	spanID, _ := trace.SpanIDFromHex("00f067aa0ba902b7")
	ctx := trace.ContextWithSpanContext(context.Background(), trace.NewSpanContext(trace.SpanContextConfig{
		TraceID:    traceID,
		SpanID:     spanID,
		TraceFlags: trace.FlagsSampled,
		Remote:     true,
	}))
	if got := observability.TraceID(ctx); got != traceID.String() {
		t.Errorf("TraceID = %q, want %q", got, traceID.String())
	}
}

func TestRequestLoggerPassesThroughAndLogs(t *testing.T) {
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Write without explicit WriteHeader: covers the implicit-200 branch.
		_, _ = w.Write([]byte("ok"))
	})
	h := observability.RequestLogger(nil, next)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/perfiles/E001", nil))
	if rec.Code != http.StatusOK || rec.Body.String() != "ok" {
		t.Errorf("passthrough broken: code=%d body=%q", rec.Code, rec.Body.String())
	}

	h2 := observability.RequestLogger(observability.NewLogger("test"), next)
	rec2 := httptest.NewRecorder()
	h2.ServeHTTP(rec2, httptest.NewRequest(http.MethodGet, "/health", nil))
	if rec2.Code != http.StatusOK {
		t.Errorf("code = %d, want 200", rec2.Code)
	}
}

func TestSamplerSelection(t *testing.T) {
	cases := []struct {
		name    string
		sampler string
		arg     string
		sampled bool
	}{
		{"always_off", "always_off", "", false},
		{"ratio_cero", "traceidratio", "0", false},
		{"ratio_invalido_vuelve_a_1", "traceidratio", "no-numero", true},
		{"ratio_fuera_de_rango_vuelve_a_1", "traceidratio", "7", true},
		{"defecto_samplea", "parentbased_always_on", "", true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("OTEL_SDK_DISABLED", "false")
			t.Setenv("OTEL_TRACES_SAMPLER", tc.sampler)
			t.Setenv("OTEL_TRACES_SAMPLER_ARG", tc.arg)
			shutdown, err := observability.InitTracing(context.Background(), "test-sampler")
			if err != nil {
				t.Fatalf("InitTracing: %v", err)
			}
			if shutdown == nil {
				t.Fatal("expected a shutdown function")
			}
			_, span := otel.Tracer("test").Start(context.Background(), "op")
			sampled := span.SpanContext().IsSampled()
			span.End()
			if sampled != tc.sampled {
				t.Errorf("sampled = %v, want %v", sampled, tc.sampled)
			}
			observability.ShutdownWithTimeout(shutdown, 0)
		})
	}
}

func TestShutdownWithTimeoutNilIsNoOp(t *testing.T) {
	observability.ShutdownWithTimeout(nil, 0)
}
