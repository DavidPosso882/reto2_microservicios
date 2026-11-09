package com.empresa.gestionempleados.observability;

import io.micrometer.prometheus.PrometheusConfig;
import io.micrometer.prometheus.PrometheusMeterRegistry;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Unitarias del endpoint /metrics: el scrape sale en formato Prometheus. */
class MetricsControllerTest {

    @Test
    @DisplayName("/metrics devuelve el texto Prometheus del registry")
    void metricsReturnsPrometheusText() {
        PrometheusMeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        registry.counter("reto8_test_counter").increment();

        MetricsController controller = new MetricsController(proveedor(registry));
        ResponseEntity<String> respuesta = controller.metrics();
        String body = respuesta.getBody();

        assertEquals(200, respuesta.getStatusCode().value());
        assertTrue(body.contains("reto8_test_counter_total"), body);
        assertTrue(body.contains("# TYPE reto8_test_counter_total counter"), body);
    }

    @Test
    @DisplayName("/metrics responde 503 si no hay registry (p. ej. en @SpringBootTest)")
    void metricsWithoutRegistryReturns503() {
        MetricsController controller = new MetricsController(proveedor(null));

        assertEquals(503, controller.metrics().getStatusCode().value());
    }

    /** ObjectProvider real de Spring con (o sin) el registry registrado. */
    private static ObjectProvider<PrometheusMeterRegistry> proveedor(PrometheusMeterRegistry registry) {
        StaticListableBeanFactory factory = new StaticListableBeanFactory();
        if (registry != null) {
            factory.addBean("prometheusMeterRegistry", registry);
        }
        return factory.getBeanProvider(PrometheusMeterRegistry.class);
    }
}
