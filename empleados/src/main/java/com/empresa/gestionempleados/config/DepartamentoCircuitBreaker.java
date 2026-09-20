package com.empresa.gestionempleados.config;

import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

import java.time.Duration;

/**
 * Fábrica del Circuit Breaker para la llamada empleados → departamentos (Reto 3).
 *
 * <p>Configuración elegida:
 * <ul>
 *   <li><b>Ventana de 5 llamadas, umbral 50 %:</b> el circuito se abre tras
 *       5 fallos consecutivos (el rango sugerido era 3-5). Solo
 *       {@link DepartamentoNoDisponibleException} cuenta como fallo: un 404
 *       (departamento inexistente) es una respuesta de negocio definitiva,
 *       no una caída, y por eso no abre el circuito.</li>
 *   <li><b>Espera en OPEN de 30 segundos</b> (rango sugerido 30-60 s): con la
 *       prueba del reto basta para ver el salto a fallback instantáneo y la
 *       recuperación sin reiniciar nada.</li>
 *   <li><b>Una llamada de prueba en HALF_OPEN</b> con transición automática:
 *       si departamentos volvió, el circuito se cierra solo; si no, se
 *       reabre sin intervención.</li>
 * </ul>
 *
 * <p>Uso programático (sin anotaciones ni AOP) a propósito: el servicio envuelve
 * solo la llamada de validación, y el 404 de negocio queda fuera del circuito.
 */
public final class DepartamentoCircuitBreaker {

    /** Nombre del circuito, visible en {@code GET /empleados/circuit/state}. */
    public static final String NOMBRE = "departamentos";

    private DepartamentoCircuitBreaker() {
    }

    /**
     * Crea una instancia nueva del circuito con la configuración del reto.
     *
     * @return el Circuit Breaker listo para envolver la validación
     */
    public static CircuitBreaker departamentos() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(5)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .permittedNumberOfCallsInHalfOpenState(1)
                .automaticTransitionFromOpenToHalfOpenEnabled(true)
                .recordExceptions(DepartamentoNoDisponibleException.class)
                .build();
        return CircuitBreaker.of(NOMBRE, config);
    }
}
