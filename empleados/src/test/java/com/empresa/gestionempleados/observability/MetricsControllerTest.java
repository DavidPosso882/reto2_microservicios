package com.empresa.gestionempleados.observability;

import io.micrometer.prometheus.PrometheusConfig;
import io.micrometer.prometheus.PrometheusMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

/** Unitarias del endpoint /metrics: el scrape sale en formato Prometheus. */
class MetricsControllerTest {

    @Test
    @DisplayName("/metrics devuelve el texto Prometheus del registry")
    void metricsReturnsPrometheusText() {
        PrometheusMeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        registry.counter("reto8_test_counter").increment();

        MetricsController controller = new MetricsController(registry);
        String body = controller.metrics();

        assertTrue(body.contains("reto8_test_counter_total"), body);
        assertTrue(body.contains("# TYPE reto8_test_counter_total counter"), body);
    }
}
