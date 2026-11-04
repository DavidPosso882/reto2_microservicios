// Package observability provides the Reto 8 instrumentation shared by the
// perfiles-service HTTP API and AMQP consumer:
//   - Prometheus metrics (HTTP requests, latency, process/Go collectors)
//   - OpenTelemetry tracing exported to Zipkin with W3C propagation
//   - JSON structured logging (timestamp, level, service, traceId, message)
package observability

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/zipkin"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

const (
	defaultZipkinEndpoint = "http://zipkin:9411/api/v2/spans"
	serviceVersion        = "1.0.0"
)

// InitTracing configures the global OpenTelemetry tracer provider with a
// Zipkin exporter and W3C tracecontext + baggage propagation. It returns a
// shutdown function that flushes pending spans.
//
// OTEL_SERVICE_NAME, OTEL_EXPORTER_ZIPKIN_ENDPOINT, OTEL_TRACES_SAMPLER,
// OTEL_TRACES_SAMPLER_ARG and OTEL_SDK_DISABLED are honored.
func InitTracing(ctx context.Context, defaultServiceName string) (func(context.Context) error, error) {
	serviceName := envOr("OTEL_SERVICE_NAME", defaultServiceName)
	endpoint := zipkinEndpoint()

	// W3C propagation is installed even when the SDK is disabled so outgoing
	// requests still forward an incoming traceparent.
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(
		propagation.TraceContext{},
		propagation.Baggage{},
	))

	if strings.EqualFold(envOr("OTEL_SDK_DISABLED", "false"), "true") {
		return func(context.Context) error { return nil }, nil
	}

	exporter, err := zipkin.New(endpoint)
	if err != nil {
		return nil, fmt.Errorf("zipkin exporter: %w", err)
	}

	res, err := resource.Merge(
		resource.Default(),
		resource.NewSchemaless(
			attribute.String("service.name", serviceName),
			attribute.String("service.version", serviceVersion),
		),
	)
	if err != nil {
		return nil, fmt.Errorf("otel resource: %w", err)
	}

	provider := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(res),
		sdktrace.WithSampler(samplerFromEnv()),
	)
	otel.SetTracerProvider(provider)

	return provider.Shutdown, nil
}

func samplerFromEnv() sdktrace.Sampler {
	switch envOr("OTEL_TRACES_SAMPLER", "parentbased_always_on") {
	case "always_off":
		return sdktrace.NeverSample()
	case "traceidratio":
		return sdktrace.TraceIDRatioBased(ratioFromEnv())
	case "parentbased_traceidratio":
		return sdktrace.ParentBased(sdktrace.TraceIDRatioBased(ratioFromEnv()))
	default:
		return sdktrace.ParentBased(sdktrace.AlwaysSample())
	}
}

func ratioFromEnv() float64 {
	ratio, err := strconv.ParseFloat(envOr("OTEL_TRACES_SAMPLER_ARG", "1"), 64)
	if err != nil || ratio < 0 || ratio > 1 {
		return 1
	}
	return ratio
}

// zipkinEndpoint accepts both the base URL and the full collector path.
func zipkinEndpoint() string {
	endpoint := strings.TrimRight(envOr("OTEL_EXPORTER_ZIPKIN_ENDPOINT", defaultZipkinEndpoint), "/")
	if strings.HasSuffix(endpoint, "/api/v2/spans") {
		return endpoint
	}
	return endpoint + "/api/v2/spans"
}

// ShutdownWithTimeout flushes the tracer provider with a bounded timeout.
func ShutdownWithTimeout(shutdown func(context.Context) error, timeout time.Duration) {
	if shutdown == nil {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	_ = shutdown(ctx)
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
