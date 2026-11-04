package com.empresa.gestionempleados.observability;

import io.micrometer.prometheus.PrometheusConfig;
import io.micrometer.prometheus.PrometheusMeterRegistry;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Garantiza el {@link PrometheusMeterRegistry} en todos los contextos.
 *
 * <p>Spring Boot lo auto-configura cuando {@code micrometer-registry-prometheus}
 * está en el classpath, pero los tests de corte controlador (@SpringBootTest con
 * H2) y cualquier contexto sin el auto-config de exportación fallaban con
 * {@code NoSuchBeanDefinitionException} en {@code MetricsController}. Con
 * {@code @ConditionalOnMissingBean} este bean es solo un respaldo: si el
 * auto-config ya lo aporta, este no se crea (sin conflictos).
 */
@Configuration
public class MetricsRegistryConfig {

    @Bean
    @ConditionalOnMissingBean(PrometheusMeterRegistry.class)
    public PrometheusMeterRegistry prometheusMeterRegistry() {
        return new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
    }
}
