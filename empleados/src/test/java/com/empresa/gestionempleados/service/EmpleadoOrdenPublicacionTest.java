package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.events.EventPublisher;
import com.empresa.gestionempleados.events.EventTypes;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

import java.util.Optional;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

/**
 * Verifica con mocks puros (sin Spring) que la publicación de eventos ocurre
 * DESPUÉS del save, usando InOrder sobre el repositorio y el publisher.
 */
class EmpleadoOrdenPublicacionTest {

    private EmpleadoRepository repository;
    private EventPublisher publisher;
    private EmpleadoService service;

    @BeforeEach
    void setUp() {
        repository = mock(EmpleadoRepository.class);
        DepartamentoClient departamentoClient = mock(DepartamentoClient.class);
        publisher = mock(EventPublisher.class);

        when(departamentoClient.validar(anyString())).thenReturn(true);
        when(repository.save(any(Empleado.class))).thenAnswer(inv -> inv.getArgument(0));
        when(repository.existsById(anyString())).thenReturn(false);
        when(repository.findByEmail(anyString())).thenReturn(Optional.empty());
        when(repository.findByNumeroEmpleado(anyString())).thenReturn(Optional.empty());

        service = new EmpleadoService(repository, departamentoClient, publisher);
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

    @Test
    @DisplayName("empleado.creado se publica después del save")
    void creadoSePublicaDespuesDelSave() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        InOrder orden = inOrder(repository, publisher);
        orden.verify(repository).save(any(Empleado.class));
        orden.verify(publisher).publicar(eq(EventTypes.EMPLEADO_CREADO), any(java.time.Instant.class), anyMap());
    }

    @Test
    @DisplayName("empleado.actualizado se publica después del save")
    void actualizadoSePublicaDespuesDelSave() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        when(repository.findById("E001")).thenReturn(
                Optional.of(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001")));

        Empleado cambios = new Empleado();
        cambios.setNombre("Juan Carlos");
        service.actualizar("E001", cambios);

        InOrder orden = inOrder(repository, publisher);
        orden.verify(repository).save(any(Empleado.class));
        orden.verify(publisher).publicar(eq(EventTypes.EMPLEADO_ACTUALIZADO), any(java.time.Instant.class), anyMap());
    }

    @Test
    @DisplayName("empleado.retirado se publica después del save")
    void retiradoSePublicaDespuesDelSave() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        when(repository.findById("E001")).thenReturn(
                Optional.of(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001")));

        service.retirar("E001");

        InOrder orden = inOrder(repository, publisher);
        orden.verify(repository).save(any(Empleado.class));
        orden.verify(publisher).publicar(eq(EventTypes.EMPLEADO_RETIRADO), any(java.time.Instant.class), anyMap());
    }
}
