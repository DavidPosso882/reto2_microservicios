package observability_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"perfiles-service/internal/observability"
)

func TestInitTracingHonorsDisabledFlag(t *testing.T) {
	t.Setenv("OTEL_SDK_DISABLED", "true")

	shutdown, err := observability.InitTracing(context.Background(), "perfiles-service")
	if err != nil {
		t.Fatalf("InitTracing: %v", err)
	}
	if shutdown == nil {
		t.Fatal("expected a shutdown function")
	}
	if err := shutdown(context.Background()); err != nil {
		t.Fatalf("shutdown: %v", err)
	}
}

func TestMetricsExposeREDAndProcessCollectors(t *testing.T) {
	metrics := observability.NewMetrics("perfiles-service")
	mux := http.NewServeMux()
	mux.HandleFunc("GET /perfiles/{empleadoId}", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	handler := metrics.Middleware(mux)

	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, httptest.NewRequest(http.MethodGet, "/perfiles/E001", nil))

	scrape := httptest.NewRecorder()
	metrics.Handler().ServeHTTP(scrape, httptest.NewRequest(http.MethodGet, "/metrics", nil))
	body := scrape.Body.String()

	for _, needle := range []string{
		"process_cpu_seconds_total",
		"go_goroutines",
		"http_requests_total",
		`route="/perfiles/:empleadoId"`,
		`code="200"`,
		"http_request_duration_seconds",
	} {
		if !strings.Contains(body, needle) {
			t.Errorf("metrics missing %q:\n%s", needle, body)
		}
	}
}

func TestNormalizeRouteKeepsCardinalityBounded(t *testing.T) {
	if got := observability.NormalizeRoute("/perfiles/E001"); got != "/perfiles/:empleadoId" {
		t.Fatalf("NormalizeRoute: %q", got)
	}
	if got := observability.NormalizeRoute("/health"); got != "/health" {
		t.Fatalf("NormalizeRoute static: %q", got)
	}
}
