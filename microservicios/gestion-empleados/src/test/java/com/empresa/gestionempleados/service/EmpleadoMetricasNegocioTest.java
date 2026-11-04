package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.events.EventPublisher;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * Contadores de negocio (T8): empleados.creados y empleados.retirados.
 *
 * <p>El servicio usa el registro global de Micrometer (sin constructor nuevo,
 * sin dependencias nuevas): en producción lo alimenta el registry de
 * Prometheus; aquí se enlaza un {@link SimpleMeterRegistry} por test.
 */
class EmpleadoMetricasNegocioTest {

    private SimpleMeterRegistry registry;
    private EmpleadoService service;

    @BeforeEach
    void setUp() {
        registry = new SimpleMeterRegistry();
        Metrics.addRegistry(registry);
        EmpleadoRepository repository = mock(EmpleadoRepository.class);
        DepartamentoClient departamentoClient = mock(DepartamentoClient.class);
        EventPublisher eventPublisher = mock(EventPublisher.class);
        when(repository.existsById(anyString())).thenReturn(false);
        when(repository.findByEmail(anyString())).thenReturn(Optional.empty());
        when(repository.findByNumeroEmpleado(anyString())).thenReturn(Optional.empty());
        when(departamentoClient.validar(anyString())).thenReturn(true);
        when(repository.save(any(Empleado.class))).thenAnswer(inv -> inv.getArgument(0));
        when(repository.findById("E1")).thenReturn(Optional.of(
                new Empleado("E1", "Juan", "Perez", "j@e.com", "N1",
                        "Dev", "Tec", "IT", "2026-02-10", EstadoEmpleado.ACTIVO)));
        service = new EmpleadoService(repository, departamentoClient, eventPublisher);
    }

    @AfterEach
    void tearDown() {
        Metrics.removeRegistry(registry);
        registry.close();
    }

    @Test
    @DisplayName("registrar incrementa empleados.creados en 1")
    void registrarCuentaCreado() {
        service.registrar(new Empleado("E9", "Juan", "Perez", "n@e.com", "N9",
                "Dev", "Tec", "IT", "2026-02-10", EstadoEmpleado.ACTIVO));
        assertEquals(1.0, registry.get("empleados.creados").counter().count());
    }

    @Test
    @DisplayName("retirar incrementa empleados.retirados en 1 (no la vía idempotente)")
    void retirarCuentaRetirado() {
        service.retirar("E1");
        assertEquals(1.0, registry.get("empleados.retirados").counter().count());
        service.retirar("E1");
        assertEquals(1.0, registry.get("empleados.retirados").counter().count());
    }
}
