package com.empresa.gestionempleados.observability;

import io.micrometer.prometheus.PrometheusMeterRegistry;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Publica el scrape de Prometheus en {@code /metrics} (Reto 8).
 *
 * <p>Spring Boot registra un {@link PrometheusMeterRegistry} cuando
 * {@code micrometer-registry-prometheus} está en el classpath; su
 * {@link PrometheusMeterRegistry#scrape()} devuelve el formato de texto
 * Prometheus con las métricas HTTP (http.server.requests), JVM y proceso.
 *
 * <p>El registry se pide con {@link ObjectProvider} y no por constructor:
 * en {@code @SpringBootTest} Spring Boot desactiva la exportación de métricas
 * y no crea el bean, y exigirlo impedía cargar el contexto de los tests de
 * controlador. Sin registry, {@code /metrics} responde 503.
 */
@RestController
public class MetricsController {

    private final ObjectProvider<PrometheusMeterRegistry> registry;

    public MetricsController(ObjectProvider<PrometheusMeterRegistry> registry) {
        this.registry = registry;
    }

    @GetMapping(value = "/metrics", produces = "text/plain;version=0.0.4;charset=utf-8")
    public ResponseEntity<String> metrics() {
        PrometheusMeterRegistry prometheus = registry.getIfAvailable();
        if (prometheus == null) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body("# Registro Prometheus no disponible\n");
        }
        return ResponseEntity.ok(prometheus.scrape());
    }
}
