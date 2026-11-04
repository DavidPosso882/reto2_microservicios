package com.empresa.gestionempleados.observability;

import io.micrometer.prometheus.PrometheusMeterRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Publica el scrape de Prometheus en {@code /metrics} (Reto 8).
 *
 * <p>Spring Boot registra un {@link PrometheusMeterRegistry} cuando
 * {@code micrometer-registry-prometheus} está en el classpath; su
 * {@link PrometheusMeterRegistry#scrape()} devuelve el formato de texto
 * Prometheus con las métricas HTTP (http.server.requests), JVM y proceso.
 */
@RestController
public class MetricsController {

    private final PrometheusMeterRegistry registry;

    public MetricsController(PrometheusMeterRegistry registry) {
        this.registry = registry;
    }

    @GetMapping(value = "/metrics", produces = "text/plain;version=0.0.4;charset=utf-8")
    public String metrics() {
        return registry.scrape();
    }
}
