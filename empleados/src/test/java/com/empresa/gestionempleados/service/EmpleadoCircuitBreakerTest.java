package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.events.EventPublisher;
import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import com.empresa.gestionempleados.exception.DepartamentoNoExisteException;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Pruebas del Circuit Breaker empleados → departamentos (Reto 3).
 *
 * <p>El circuito vive en el bean del servicio y sus métricas se acumulan entre
 * tests del mismo contexto: por eso cada test parte de {@code reset()} y la
 * clase cierra con {@code AFTER_CLASS} para no contaminar a
 * {@link EmpleadoServiceTest} (comparten el contexto cacheado).
 */
@DataJpaTest
@Import(EmpleadoService.class)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class EmpleadoCircuitBreakerTest {

    @Autowired
    private EmpleadoRepository repository;

    @Autowired
    private EmpleadoService service;

    @MockBean
    private DepartamentoClient departamentoClient;

    @MockBean
    private EventPublisher eventPublisher;

    @BeforeEach
    void setUp() {
        service.getCircuitoDepartamentos().reset();
        when(departamentoClient.validar(anyString())).thenReturn(true);
    }

    private Empleado empleadoValido(String id, String email, String numeroEmpleado) {
        return new Empleado(
                id,
                "Juan",
                "Perez",
                email,
                numeroEmpleado,
                "Desarrollador Senior",
                "Tecnologia",
                "IT",
                "2026-02-10",
                EstadoEmpleado.ACTIVO
        );
    }

    private void provocarCincoFallos() {
        when(departamentoClient.validar(anyString())).thenThrow(new DepartamentoNoDisponibleException());
        for (int i = 1; i <= 5; i++) {
            Empleado registrado = service.registrar(
                    empleadoValido("E-CB-" + i, "cb" + i + "@empresa.com", "EMP-CB-" + i));
            assertEquals(EstadoEmpleado.PENDIENTE_VALIDACION, registrado.getEstado(),
                    "Cada fallo debe degradar a PENDIENTE_VALIDACION");
        }
    }

    @Test
    @DisplayName("tras 5 fallos consecutivos el circuito se abre (OPEN)")
    void cincoFallosConsecutivosAbrenElCircuito() {
        provocarCincoFallos();

        assertEquals(CircuitBreaker.State.OPEN, service.getCircuitoDepartamentos().getState(),
                "El circuito debe abrirse tras 5 fallos consecutivos");
    }

    @Test
    @DisplayName("con el circuito abierto el fallback es inmediato y no toca la red")
    void circuitoAbiertoBloqueaLaLlamadaSinTocarLaRed() {
        provocarCincoFallos();

        Empleado registrado = service.registrar(
                empleadoValido("E-CB-6", "cb6@empresa.com", "EMP-CB-6"));

        assertEquals(EstadoEmpleado.PENDIENTE_VALIDACION, registrado.getEstado());
        // Solo las 5 llamadas que abrieron el circuito llegaron al cliente;
        // la sexta se bloqueó localmente (comportamiento OPEN).
        verify(departamentoClient, times(5)).validar(anyString());
        assertEquals(1, service.getCircuitoDepartamentos().getMetrics().getNumberOfNotPermittedCalls(),
                "La llamada bloqueada debe contarse como no permitida");
    }

    @Test
    @DisplayName("en HALF_OPEN un éxito cierra el circuito (recuperación automática)")
    void halfOpenConExitoCierraElCircuito() {
        provocarCincoFallos();
        service.getCircuitoDepartamentos().transitionToHalfOpenState();

        // doReturn: re-stubear con when() ejecutaría el stub anterior (thenThrow)
        // y la excepción escaparía del stubbing en lugar de registrarse.
        doReturn(true).when(departamentoClient).validar(anyString());
        Empleado registrado = service.registrar(
                empleadoValido("E-CB-R", "cbr@empresa.com", "EMP-CB-R"));

        assertEquals(EstadoEmpleado.ACTIVO, registrado.getEstado(),
                "La llamada de prueba exitosa debe validar de verdad y cerrar el circuito");
        assertEquals(CircuitBreaker.State.CLOSED, service.getCircuitoDepartamentos().getState());
    }

    @Test
    @DisplayName("en HALF_OPEN un fallo reabre el circuito")
    void halfOpenConFalloReabreElCircuito() {
        provocarCincoFallos();
        service.getCircuitoDepartamentos().transitionToHalfOpenState();

        Empleado registrado = service.registrar(
                empleadoValido("E-CB-R2", "cbr2@empresa.com", "EMP-CB-R2"));

        assertEquals(EstadoEmpleado.PENDIENTE_VALIDACION, registrado.getEstado());
        assertEquals(CircuitBreaker.State.OPEN, service.getCircuitoDepartamentos().getState(),
                "Si la prueba falla, el circuito debe volver a abrirse");
    }

    @Test
    @DisplayName("revalidar reconcilia un PENDIENTE_VALIDACION a ACTIVO cuando departamentos vuelve")
    void revalidarReconciliaPendienteAActivo() {
        when(departamentoClient.validar(anyString())).thenThrow(new DepartamentoNoDisponibleException());
        service.registrar(empleadoValido("E-CB-P", "cbp@empresa.com", "EMP-CB-P"));

        doReturn(true).when(departamentoClient).validar(anyString());
        Empleado reconciliado = service.revalidar("E-CB-P");

        assertEquals(EstadoEmpleado.ACTIVO, reconciliado.getEstado());
        assertEquals(EstadoEmpleado.ACTIVO, service.buscarPorId("E-CB-P").getEstado(),
                "La reconciliación debe persistirse");
    }

    @Test
    @DisplayName("revalidar con departamento inexistente rechaza con 400 y mantiene el pendiente")
    void revalidarConDepartamentoInexistenteRechaza() {
        when(departamentoClient.validar(anyString())).thenThrow(new DepartamentoNoDisponibleException());
        service.registrar(empleadoValido("E-CB-P2", "cbp2@empresa.com", "EMP-CB-P2"));

        doReturn(false).when(departamentoClient).validar("NODEP");
        Empleado pendiente = service.buscarPorId("E-CB-P2");
        pendiente.setDepartamentoId("NODEP");
        repository.save(pendiente);

        assertThrows(
                DepartamentoNoExisteException.class,
                () -> service.revalidar("E-CB-P2"),
                "Revalidar contra un departamento inexistente debe rechazarse");
        assertEquals(EstadoEmpleado.PENDIENTE_VALIDACION, service.buscarPorId("E-CB-P2").getEstado(),
                "El empleado sigue pendiente hasta reconciliarse de verdad");
    }

    @Test
    @DisplayName("estadoCircuito expone nombre, estado y métricas")
    void estadoCircuitoExponeMetricas() {
        provocarCincoFallos();

        var estado = service.estadoCircuito();

        assertEquals("departamentos", estado.get("nombre"));
        assertEquals("OPEN", estado.get("estado"));
        assertEquals(5, ((Number) estado.get("llamadasFallidas")).intValue());
    }
}
