package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.events.EventPublisher;
import com.empresa.gestionempleados.events.EventTypes;
import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import com.empresa.gestionempleados.exception.DepartamentoNoExisteException;
import com.empresa.gestionempleados.exception.EmpleadoDuplicadoException;
import com.empresa.gestionempleados.exception.EmpleadoNotFoundException;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * Unitarias puras de {@link EmpleadoService} con Mockito (Reto 6, Punto 1).
 *
 * <p>Sin contexto de Spring y sin Docker: repositorio, cliente de
 * departamentos y publisher son dobles controlados. Cubren duplicados,
 * la transición de baja lógica (RETIRADO + fechaRetiro), el rechazo de
 * transiciones no aplicables y varios caminos de error.
 */
class EmpleadoServiceMockitoTest {

    private EmpleadoRepository repository;
    private DepartamentoClient departamentoClient;
    private EventPublisher eventPublisher;
    private EmpleadoService service;

    @BeforeEach
    void setUp() {
        repository = mock(EmpleadoRepository.class);
        departamentoClient = mock(DepartamentoClient.class);
        eventPublisher = mock(EventPublisher.class);
        service = new EmpleadoService(repository, departamentoClient, eventPublisher);
    }

    private Empleado empleado(String id, String email, String numeroEmpleado) {
        return new Empleado(id, "Juan", "Perez", email, numeroEmpleado,
                "Desarrollador Senior", "Tecnologia", "IT", "2026-02-10", EstadoEmpleado.ACTIVO);
    }

    private void stubsDeRegistroValido() {
        when(repository.existsById(anyString())).thenReturn(false);
        when(repository.save(any(Empleado.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(departamentoClient.validar("IT")).thenReturn(true);
    }

    @Test
    @DisplayName("email duplicado: rechaza con EmpleadoDuplicadoException y no persiste")
    void emailDuplicadoRechazaSinPersistir() {
        Empleado existente = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        when(repository.findByEmail("juan.perez@empresa.com")).thenReturn(Optional.of(existente));

        EmpleadoDuplicadoException ex = assertThrows(
                EmpleadoDuplicadoException.class,
                () -> service.registrar(empleado("E002", "juan.perez@empresa.com", "EMP-2026-002")));

        assertTrue(ex.getMessage().contains("juan.perez@empresa.com"));
        verify(repository, never()).save(any(Empleado.class));
    }

    @Test
    @DisplayName("numeroEmpleado duplicado: rechaza con EmpleadoDuplicadoException y no persiste")
    void numeroEmpleadoDuplicadoRechazaSinPersistir() {
        Empleado existente = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        when(repository.findByNumeroEmpleado("EMP-2026-001")).thenReturn(Optional.of(existente));

        EmpleadoDuplicadoException ex = assertThrows(
                EmpleadoDuplicadoException.class,
                () -> service.registrar(empleado("E002", "otro@empresa.com", "EMP-2026-001")));

        assertTrue(ex.getMessage().contains("EMP-2026-001"));
        verify(repository, never()).save(any(Empleado.class));
    }

    @Test
    @DisplayName("registro válido: fuerza ACTIVO, persiste y publica empleado.creado")
    void registroValidoFuerzaActivoYPublica() {
        stubsDeRegistroValido();
        Empleado conEstadoManipulado = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        conEstadoManipulado.setEstado(EstadoEmpleado.EN_VACACIONES);

        Empleado registrado = service.registrar(conEstadoManipulado);

        assertEquals(EstadoEmpleado.ACTIVO, registrado.getEstado());
        verify(repository).save(conEstadoManipulado);
        verify(eventPublisher).publicar(eq(EventTypes.EMPLEADO_CREADO), any(Instant.class), anyMap());
    }

    @Test
    @DisplayName("retirar: transiciona a RETIRADO con fechaRetiro ISO-8601 UTC y publica empleado.retirado")
    void retirarTransicionaConFechaRetiroYPublica() {
        Empleado activo = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        when(repository.findById("E001")).thenReturn(Optional.of(activo));
        when(repository.save(any(Empleado.class))).thenAnswer(invocation -> invocation.getArgument(0));
        Instant antes = Instant.now();

        Empleado retirado = service.retirar("E001");

        assertSame(activo, retirado);
        assertEquals(EstadoEmpleado.RETIRADO, retirado.getEstado());
        assertNotNull(retirado.getFechaRetiro());
        Instant fechaRetiro = assertDoesNotThrow(() -> Instant.parse(retirado.getFechaRetiro()),
                "fechaRetiro debe ser ISO-8601 UTC parseable");
        assertFalse(fechaRetiro.isBefore(antes.minusSeconds(1)));
        assertFalse(fechaRetiro.isAfter(Instant.now().plusSeconds(1)));

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, Object>> data = ArgumentCaptor.forClass(Map.class);
        ArgumentCaptor<Instant> occurredAt = ArgumentCaptor.forClass(Instant.class);
        verify(eventPublisher).publicar(eq(EventTypes.EMPLEADO_RETIRADO), occurredAt.capture(), data.capture());

        assertEquals(fechaRetiro, occurredAt.getValue(), "occurredAt debe ser la fechaRetiro del hecho");
        assertEquals("E001", data.getValue().get("id"));
        assertEquals("RETIRADO", data.getValue().get("estado"));
        assertEquals(retirado.getFechaRetiro(), data.getValue().get("fechaRetiro"));
    }

    @Test
    @DisplayName("retirar es idempotente: un RETIRADO no vuelve a guardarse ni a publicar")
    void retirarIdempotenteNoRepublica() {
        Empleado yaRetirado = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        yaRetirado.setEstado(EstadoEmpleado.RETIRADO);
        yaRetirado.setFechaRetiro("2026-09-01T10:00:00Z");
        when(repository.findById("E001")).thenReturn(Optional.of(yaRetirado));

        Empleado resultado = service.retirar("E001");

        assertSame(yaRetirado, resultado);
        assertEquals("2026-09-01T10:00:00Z", resultado.getFechaRetiro());
        verify(repository, never()).save(any(Empleado.class));
        verifyNoInteractions(eventPublisher);
    }

    @Test
    @DisplayName("revalidar rechaza la transición no aplicable: un ACTIVO no se revalida ni toca la red")
    void revalidarRechazaTransicionNoAplicable() {
        Empleado activo = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        when(repository.findById("E001")).thenReturn(Optional.of(activo));

        Empleado resultado = service.revalidar("E001");

        assertSame(activo, resultado);
        assertEquals(EstadoEmpleado.ACTIVO, resultado.getEstado());
        verifyNoInteractions(departamentoClient);
        verify(repository, never()).save(any(Empleado.class));
        verifyNoInteractions(eventPublisher);
    }

    @Test
    @DisplayName("revalidar un PENDIENTE_VALIDACION con departamento vivo lo reconcilia a ACTIVO")
    void revalidarPendienteLoReconcilia() {
        Empleado pendiente = empleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        pendiente.setEstado(EstadoEmpleado.PENDIENTE_VALIDACION);
        pendiente.setMensaje("Empleado registrado. Validación de departamento pendiente.");
        when(repository.findById("E001")).thenReturn(Optional.of(pendiente));
        when(departamentoClient.validar("IT")).thenReturn(true);
        when(repository.save(any(Empleado.class))).thenAnswer(invocation -> invocation.getArgument(0));

        Empleado resultado = service.revalidar("E001");

        assertEquals(EstadoEmpleado.ACTIVO, resultado.getEstado());
        assertNull(resultado.getMensaje());
        verify(departamentoClient).validar("IT");
        verify(repository).save(pendiente);
    }

    @Test
    @DisplayName("registrar con departamento inexistente lanza DepartamentoNoExisteException sin persistir")
    void registrarDepartamentoInexistenteFalla() {
        when(repository.existsById(anyString())).thenReturn(false);
        when(departamentoClient.validar("IT")).thenReturn(false);

        DepartamentoNoExisteException ex = assertThrows(
                DepartamentoNoExisteException.class,
                () -> service.registrar(empleado("E001", "juan.perez@empresa.com", "EMP-2026-001")));

        assertEquals("El departamento con id 'IT' no existe", ex.getMessage());
        verify(repository, never()).save(any(Empleado.class));
        verifyNoInteractions(eventPublisher);
    }

    @Test
    @DisplayName("departamentos caído: registra como PENDIENTE_VALIDACION (fallback) y publica el estado real")
    void departamentosCaidoRegistraPendiente() {
        when(repository.existsById(anyString())).thenReturn(false);
        when(repository.save(any(Empleado.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(departamentoClient.validar(anyString())).thenThrow(new DepartamentoNoDisponibleException());

        Empleado registrado = service.registrar(empleado("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        assertEquals(EstadoEmpleado.PENDIENTE_VALIDACION, registrado.getEstado());
        assertNotNull(registrado.getMensaje());
        verify(repository).save(any(Empleado.class));
        verify(eventPublisher).publicar(eq(EventTypes.EMPLEADO_CREADO), any(Instant.class), anyMap());
    }

    @Test
    @DisplayName("buscarPorId inexistente lanza EmpleadoNotFoundException (camino de error)")
    void buscarPorIdInexistenteFalla() {
        EmpleadoNotFoundException ex = assertThrows(
                EmpleadoNotFoundException.class,
                () -> service.buscarPorId("E999"));

        assertEquals("El empleado con id E999 no existe", ex.getMessage());
    }

    @Test
    @DisplayName("un fallo del publisher no revierte el registro (best-effort)")
    void falloDelPublisherNoRevierteElRegistro() {
        stubsDeRegistroValido();
        doThrow(new RuntimeException("broker caído"))
                .when(eventPublisher).publicar(eq(EventTypes.EMPLEADO_CREADO), any(Instant.class), anyMap());

        Empleado registrado = service.registrar(empleado("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        assertNotNull(registrado);
        assertEquals(EstadoEmpleado.ACTIVO, registrado.getEstado());
        verify(repository).save(any(Empleado.class));
    }
}
