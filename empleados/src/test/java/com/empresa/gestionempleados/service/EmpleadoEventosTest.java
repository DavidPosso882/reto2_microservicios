package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.config.RabbitMQConfig;
import com.empresa.gestionempleados.events.EventTypes;
import com.empresa.gestionempleados.events.RabbitEventPublisher;
import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import com.empresa.gestionempleados.exception.DepartamentoNoExisteException;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Tests de publicación de eventos y auditoría (Reto 4).
 *
 * <p>La capa de persistencia es real (JPA + H2) y el publisher AMQP es real:
 * el envelope (id/type/version/occurredAt/producer/data) lo construye
 * {@link RabbitEventPublisher} según el catálogo normativo
 * (CATALOGO_EVENTOS.md); solo el transporte (AmqpTemplate) se mockea.
 * Publicar jamás debe romper el flujo de negocio.
 */
@DataJpaTest
@Import({EmpleadoService.class, RabbitEventPublisher.class})
class EmpleadoEventosTest {

    @Autowired
    private EmpleadoRepository repository;

    @Autowired
    private EmpleadoService service;

    @MockBean
    private DepartamentoClient departamentoClient;

    @MockBean
    private AmqpTemplate amqp;

    @BeforeEach
    void setUp() {
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

    /**
     * Captura el envelope publicado al exchange del ecosistema para un type.
     * Solo puede existir una publicación de ese type en el escenario.
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> eventoPublicado(String type) {
        ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
        verify(amqp, times(1))
                .convertAndSend(eq(RabbitMQConfig.EVENTOS_EXCHANGE), eq(type), captor.capture());
        return (Map<String, Object>) captor.getValue();
    }

    @Test
    @DisplayName("registrar ACTIVO publica empleado.creado con envelope y foto completa del catálogo")
    void registrarActivoPublicaEmpleadoCreadoConFotoCompleta() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        Map<String, Object> evento = eventoPublicado(EventTypes.EMPLEADO_CREADO);

        assertEquals(EventTypes.EMPLEADO_CREADO, evento.get("type"));
        assertEquals("1.0", evento.get("version"));
        assertEquals("empleados-service", evento.get("producer"));
        assertNotNull(evento.get("id"), "El envelope debe traer un id de deduplicación");
        UUID id = UUID.fromString(evento.get("id").toString());
        assertEquals(4, id.version(), "El id del envelope debe ser UUID v4");
        assertNotNull(evento.get("occurredAt"));
        assertTrue(evento.get("occurredAt").toString().matches("^\\d{4}-\\d{2}-\\d{2}T.*Z$"),
                "occurredAt debe ser ISO-8601 UTC");

        @SuppressWarnings("unchecked")
        Map<String, Object> data = (Map<String, Object>) evento.get("data");
        assertEquals("E001", data.get("id"));
        assertEquals("Juan", data.get("nombre"));
        assertEquals("Perez", data.get("apellido"));
        assertEquals("juan.perez@empresa.com", data.get("email"));
        assertEquals("EMP-2026-001", data.get("numeroEmpleado"));
        assertEquals("Desarrollador Senior", data.get("cargo"));
        assertEquals("Tecnologia", data.get("area"));
        assertEquals("IT", data.get("departamentoId"));
        assertEquals("2026-02-10", data.get("fechaIngreso"));
        assertEquals("ACTIVO", data.get("estado"));
    }

    @Test
    @DisplayName("registrar en fallback PENDIENTE_VALIDACION también publica empleado.creado con el estado real")
    void registrarEnFallbackPendienteTambienPublicaCreadoConEstadoReal() {
        when(departamentoClient.validar(anyString()))
                .thenThrow(new DepartamentoNoDisponibleException());

        Empleado registrado = service.registrar(
                empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        assertEquals(EstadoEmpleado.PENDIENTE_VALIDACION, registrado.getEstado());

        Map<String, Object> evento = eventoPublicado(EventTypes.EMPLEADO_CREADO);

        @SuppressWarnings("unchecked")
        Map<String, Object> data = (Map<String, Object>) evento.get("data");
        assertEquals("PENDIENTE_VALIDACION", data.get("estado"),
                "El evento debe publicarse también en fallback, con el estado real");
    }

    @Test
    @DisplayName("actualizar publica empleado.actualizado con la foto completa ya actualizada")
    void actualizarPublicaEmpleadoActualizadoConFotoCompleta() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        Empleado cambios = new Empleado();
        cambios.setNombre("Juan Carlos");
        cambios.setEmail("juan.carlos@empresa.com");
        cambios.setCargo("Tech Lead");
        service.actualizar("E001", cambios);

        Map<String, Object> evento = eventoPublicado(EventTypes.EMPLEADO_ACTUALIZADO);
        assertEquals(EventTypes.EMPLEADO_ACTUALIZADO, evento.get("type"));
        assertEquals("1.0", evento.get("version"));
        assertEquals("empleados-service", evento.get("producer"));

        @SuppressWarnings("unchecked")
        Map<String, Object> data = (Map<String, Object>) evento.get("data");
        assertEquals("E001", data.get("id"));
        assertEquals("Juan Carlos", data.get("nombre"), "El evento debe reflejar el valor nuevo");
        assertEquals("juan.carlos@empresa.com", data.get("email"));
        assertEquals("Tech Lead", data.get("cargo"));
        assertEquals("Perez", data.get("apellido"), "La foto es completa: los campos no tocados viajan igual");
        assertEquals("ACTIVO", data.get("estado"));
    }

    @Test
    @DisplayName("la publicación ocurre DESPUÉS del save: el evento refleja el estado persistido")
    void laPublicacionOcurreDespuesDelSave() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        service.retirar("E001");

        Map<String, Object> evento = eventoPublicado(EventTypes.EMPLEADO_RETIRADO);

        @SuppressWarnings("unchecked")
        Map<String, Object> data = (Map<String, Object>) evento.get("data");
        // Si el save hubiera corrido después, la foto tendría el estado viejo.
        assertEquals("RETIRADO", data.get("estado"),
                "El evento publicado después del save debe llevar el estado ya persistido");
        assertEquals(EstadoEmpleado.RETIRADO, service.buscarPorId("E001").getEstado());
    }

    @Test
    @DisplayName("fallo de publicación en registrar no revierte la base de datos")
    void falloDePublicacionEnRegistrarNoRevierteLaBD() {
        doThrow(new RuntimeException("broker caído"))
                .when(amqp).convertAndSend(anyString(), anyString(), any(Object.class));

        Empleado registrado = service.registrar(
                empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        assertEquals("E001", registrado.getId(), "El registro debe seguir siendo exitoso");
        assertEquals(1, repository.count(), "El empleado debe quedar persistido aunque el publish falle");
        assertEquals(EstadoEmpleado.ACTIVO, service.buscarPorId("E001").getEstado());
    }

    @Test
    @DisplayName("fallo de publicación en retirar no revierte la baja lógica")
    void falloDePublicacionEnRetirarNoRevierteLaBD() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        doThrow(new RuntimeException("broker caído"))
                .when(amqp).convertAndSend(anyString(), anyString(), any(Object.class));

        Empleado retirado = service.retirar("E001");

        assertEquals(EstadoEmpleado.RETIRADO, retirado.getEstado(),
                "La baja lógica debe persistirse aunque el publish falle");
        assertEquals(EstadoEmpleado.RETIRADO, service.buscarPorId("E001").getEstado());
    }

    @Test
    @DisplayName("retirar publica empleado.retirado con fechaRetiro y occurredAt iguales")
    void retirarPublicaEmpleadoRetirado() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        Empleado retirado = service.retirar("E001");

        assertNotNull(retirado.getFechaRetiro(), "La baja lógica debe registrar fechaRetiro");
        assertNull(service.buscarPorId("E001").getMensaje());

        Map<String, Object> evento = eventoPublicado(EventTypes.EMPLEADO_RETIRADO);
        assertEquals(EventTypes.EMPLEADO_RETIRADO, evento.get("type"));

        @SuppressWarnings("unchecked")
        Map<String, Object> data = (Map<String, Object>) evento.get("data");
        assertEquals("E001", data.get("id"));
        assertEquals("juan.perez@empresa.com", data.get("email"));
        assertEquals("RETIRADO", data.get("estado"));
        assertEquals(retirado.getFechaRetiro(), data.get("fechaRetiro"));
        assertEquals(data.get("fechaRetiro"), evento.get("occurredAt"),
                "En empleado.retirado el occurredAt debe ser la fechaRetiro");
    }

    @Test
    @DisplayName("retirar es idempotente: segunda llamada no vuelve a publicar ni cambia fechaRetiro")
    void retirarEsIdempotente() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        Empleado primero = service.retirar("E001");
        String fechaRetiro = primero.getFechaRetiro();
        Empleado segundo = service.retirar("E001");

        assertEquals(fechaRetiro, segundo.getFechaRetiro(),
                "La fechaRetiro no debe cambiar en llamadas repetidas");
        assertEquals(EstadoEmpleado.RETIRADO, segundo.getEstado());
        verify(amqp, times(1)).convertAndSend(eq(RabbitMQConfig.EVENTOS_EXCHANGE),
                eq(EventTypes.EMPLEADO_RETIRADO), any(Object.class));
    }

    @Test
    @DisplayName("actualizar con email sin cambios no revalida el departamento")
    void actualizarSinCambiosRelevantesNoRevalidaDepartamento() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        Empleado cambios = new Empleado();
        cambios.setNombre("Juan Carlos");
        cambios.setEmail("juan.perez@empresa.com"); // mismo email
        service.actualizar("E001", cambios);

        assertEquals("Juan Carlos", service.buscarPorId("E001").getNombre());
        // 1 vez del registrar; el actualizar no debe volver a llamar a departamentos
        verify(departamentoClient, times(1)).validar(anyString());
        verify(amqp, times(1)).convertAndSend(eq(RabbitMQConfig.EVENTOS_EXCHANGE),
                eq(EventTypes.EMPLEADO_ACTUALIZADO), any(Object.class));
    }

    @Test
    @DisplayName("actualizar con departamento inexistente lanza 404 de negocio y no publica")
    void actualizarConDepartamentoInexistenteLanza404() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        when(departamentoClient.validar("NODEP")).thenReturn(false);

        Empleado cambios = new Empleado();
        cambios.setDepartamentoId("NODEP");

        assertThrows(DepartamentoNoExisteException.class, () -> service.actualizar("E001", cambios));

        verify(amqp, times(0)).convertAndSend(eq(RabbitMQConfig.EVENTOS_EXCHANGE),
                eq(EventTypes.EMPLEADO_ACTUALIZADO), any(Object.class));
        assertEquals("IT", service.buscarPorId("E001").getDepartamentoId(),
                "El empleado debe quedar con su departamento original");
    }

    @Test
    @DisplayName("actualizar con departamentos caído lanza DepartamentoNoDisponibleException y no publica")
    void actualizarConDepartamentosCaidoLanza503() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        when(departamentoClient.validar("RRHH")).thenThrow(new DepartamentoNoDisponibleException());

        Empleado cambios = new Empleado();
        cambios.setDepartamentoId("RRHH");

        assertThrows(DepartamentoNoDisponibleException.class, () -> service.actualizar("E001", cambios));

        verify(amqp, times(0)).convertAndSend(eq(RabbitMQConfig.EVENTOS_EXCHANGE),
                eq(EventTypes.EMPLEADO_ACTUALIZADO), any(Object.class));
        assertEquals("IT", service.buscarPorId("E001").getDepartamentoId());
        assertEquals("juan.perez@empresa.com", service.buscarPorId("E001").getEmail());
    }

    @Test
    @DisplayName("actualizar revalida unicidad de email solo si cambió")
    void actualizarRevalidaEmailSoloSiCambio() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        service.registrar(empleadoValido("E002", "maria.perez@empresa.com", "EMP-2026-002"));

        Empleado cambios = new Empleado();
        cambios.setEmail("maria.perez@empresa.com");

        assertThrows(com.empresa.gestionempleados.exception.EmpleadoDuplicadoException.class,
                () -> service.actualizar("E001", cambios));
        assertEquals("juan.perez@empresa.com", service.buscarPorId("E001").getEmail());
    }

    @Test
    @DisplayName("listarConFiltros sin estado devuelve todos")
    void listarConFiltrosSinEstadoDevuelveTodos() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        service.registrar(empleadoValido("E002", "maria.perez@empresa.com", "EMP-2026-002"));
        service.retirar("E001");

        assertEquals(2, service.listarConFiltros(null, null, null).size());
    }

    @Test
    @DisplayName("listarConFiltros por estado filtra por igualdad exacta")
    void listarConFiltrosPorEstado() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        service.registrar(empleadoValido("E002", "maria.perez@empresa.com", "EMP-2026-002"));
        service.retirar("E001");

        List<Empleado> retirados = service.listarConFiltros(EstadoEmpleado.RETIRADO, null, null);
        List<Empleado> activos = service.listarConFiltros(EstadoEmpleado.ACTIVO, null, null);

        assertEquals(1, retirados.size());
        assertEquals("E001", retirados.get(0).getId());
        assertEquals(1, activos.size());
        assertEquals("E002", activos.get(0).getId());
    }

    @Test
    @DisplayName("listarConFiltros RETIRADO con rango desde/hasta filtra por fechaRetiro inclusiva")
    void listarConFiltrosRangoFechaRetiro() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        service.registrar(empleadoValido("E002", "maria.perez@empresa.com", "EMP-2026-002"));
        service.retirar("E001");
        service.retirar("E002");

        // Se fijan fechaRetiro conocidas para probar el rango de forma determinista.
        Empleado e1 = service.buscarPorId("E001");
        e1.setFechaRetiro("2026-01-15T10:00:00Z");
        repository.save(e1);
        Empleado e2 = service.buscarPorId("E002");
        e2.setFechaRetiro("2026-06-01T10:00:00Z");
        repository.save(e2);

        assertEquals(1, service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-01-01", "2026-01-31").size(),
                "Solo E001 cae en enero");
        assertEquals("E001", service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-01-01", "2026-01-31").get(0).getId());
        assertEquals(2, service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-01-01", "2026-12-31").size());
        assertEquals(0, service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-07-01", "2026-12-31").size());
        // Límites inclusivos: el mismo día de fechaRetiro entra en el rango
        assertEquals(1, service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-01-15", "2026-01-15").size());
        // Solo desde, o solo hasta
        assertEquals(2, service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-01-01", null).size());
        assertEquals(1, service.listarConFiltros(EstadoEmpleado.RETIRADO, null, "2026-05-31").size());
        assertFalse(service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-07-01", null).contains(e1));
        assertTrue(service.listarConFiltros(EstadoEmpleado.RETIRADO, "2026-06-01", null).contains(e2));
    }
}
