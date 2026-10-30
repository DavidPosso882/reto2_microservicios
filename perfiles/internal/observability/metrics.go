package observability

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Metrics owns the service Prometheus registry. A dedicated registry keeps
// the endpoint deterministic (process + Go collectors + HTTP RED metrics).
type Metrics struct {
	Registry *prometheus.Registry

	service  string
	requests *prometheus.CounterVec
	duration *prometheus.HistogramVec
}

// NewMetrics builds the registry and registers the HTTP instruments.
func NewMetrics(service string) *Metrics {
	registry := prometheus.NewRegistry()
	registry.MustRegister(prometheus.NewProcessCollector(prometheus.ProcessCollectorOpts{}))
	registry.MustRegister(prometheus.NewGoCollector())

	requests := prometheus.NewCounterVec(prometheus.CounterOpts{
		Name: "http_requests_total",
		Help: "Total de peticiones HTTP por metodo, ruta y codigo",
	}, []string{"service", "method", "route", "code"})

	duration := prometheus.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "http_request_duration_seconds",
		Help:    "Duracion de peticiones HTTP en segundos",
		Buckets: prometheus.DefBuckets,
	}, []string{"service", "method", "route", "code"})

	registry.MustRegister(requests, duration)

	return &Metrics{
		Registry: registry,
		service:  service,
		requests: requests,
		duration: duration,
	}
}

// Handler exposes the registry in Prometheus text format.
func (m *Metrics) Handler() http.Handler {
	return promhttp.HandlerFor(m.Registry, promhttp.HandlerOpts{})
}

// Middleware records request count and latency. Route labels are normalized
// (employee ids replaced by :empleadoId) to keep cardinality bounded.
func (m *Metrics) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/metrics" {
			next.ServeHTTP(w, r)
			return
		}
		started := time.Now()
		recorder := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(recorder, r)

		labels := prometheus.Labels{
			"service": m.service,
			"method":  r.Method,
			"route":   NormalizeRoute(r.URL.Path),
			"code":    strconv.Itoa(recorder.status),
		}
		m.requests.With(labels).Inc()
		m.duration.With(labels).Observe(time.Since(started).Seconds())
	})
}

// NormalizeRoute maps dynamic path segments to stable route labels.
func NormalizeRoute(path string) string {
	if strings.HasPrefix(path, "/perfiles/") && path != "/perfiles/" {
		return "/perfiles/:empleadoId"
	}
	return path
}

type statusRecorder struct {
	http.ResponseWriter
	status      int
	wroteHeader bool
}

func (r *statusRecorder) WriteHeader(status int) {
	if r.wroteHeader {
		return
	}
	r.status = status
	r.wroteHeader = true
	r.ResponseWriter.WriteHeader(status)
}

func (r *statusRecorder) Write(payload []byte) (int, error) {
	if !r.wroteHeader {
		r.WriteHeader(http.StatusOK)
	}
	return r.ResponseWriter.Write(payload)
}
