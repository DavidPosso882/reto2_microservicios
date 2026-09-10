package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
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
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.annotation.DirtiesContext;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

/**
 * Tests del servicio de empleados sobre una base de datos H2 real (Spring Data JPA).
 *
 * La llamada al servicio de departamentos se stubea con {@link MockBean}: no hay
 * dependencia viva en los tests. La capa de persistencia sí es real (JPA + H2),
 * de modo que se validan también los finders y las restricciones UNIQUE.
 */
@DataJpaTest
@Import(EmpleadoService.class)
class EmpleadoServiceTest {

    @Autowired
    private EmpleadoRepository repository;

    @Autowired
    private EmpleadoService service;

    @MockBean
    private DepartamentoClient departamentoClient;

    @BeforeEach
    void setUp() {
        // Por defecto el departamento existe; cada test concreto puede sobrescribirlo.
        when(departamentoClient.validar(anyString())).thenReturn(true);
    }

    /**
     * Crea un empleado válido con los datos dados.
     */
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
     * Resultado de un intento de registro concurrente.
     */
    private enum ResultadoRegistro {
        EXITOSO,
        DUPLICADO
    }

    @Test
    @DisplayName("registrar un empleado válido devuelve el empleado con estado ACTIVO")
    void registrarEmpleadoValidoDevuelveEmpleadoConEstadoActivo() {
        Empleado registrado = service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        assertEquals("E001", registrado.getId(), "El empleado registrado debe conservar su id");
        assertEquals(EstadoEmpleado.ACTIVO, registrado.getEstado(), "El empleado registrado debe quedar ACTIVO");
        assertEquals(1, repository.count(), "El empleado debe persistirse en la base de datos");
    }

    @Test
    @DisplayName("registrar con email duplicado lanza EmpleadoDuplicadoException")
    void registrarConEmailDuplicadoLanzaEmpleadoDuplicadoException() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        EmpleadoDuplicadoException ex = assertThrows(
                EmpleadoDuplicadoException.class,
                () -> service.registrar(empleadoValido("E002", "juan.perez@empresa.com", "EMP-2026-002")),
                "Debe rechazarse un email ya registrado"
        );
        assertTrue(ex.getMessage().contains("juan.perez@empresa.com"),
                "El mensaje debe mencionar el email duplicado");
    }

    @Test
    @DisplayName("registrar con numeroEmpleado duplicado lanza EmpleadoDuplicadoException")
    void registrarConNumeroEmpleadoDuplicadoLanzaEmpleadoDuplicadoException() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        EmpleadoDuplicadoException ex = assertThrows(
                EmpleadoDuplicadoException.class,
                () -> service.registrar(empleadoValido("E002", "otro.perez@empresa.com", "EMP-2026-001")),
                "Debe rechazarse un numeroEmpleado ya registrado"
        );
        assertTrue(ex.getMessage().contains("EMP-2026-001"),
                "El mensaje debe mencionar el numeroEmpleado duplicado");
    }

    @Test
    @DisplayName("registrar con id duplicado lanza EmpleadoDuplicadoException en lugar de sobrescribir (B3)")
    void registrarConIdDuplicadoLanzaEmpleadoDuplicadoException() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        EmpleadoDuplicadoException ex = assertThrows(
                EmpleadoDuplicadoException.class,
                () -> service.registrar(empleadoValido("E001", "otro.perez@empresa.com", "EMP-2026-002")),
                "Debe rechazarse un id ya registrado sin sobrescribir el registro previo"
        );
        assertTrue(ex.getMessage().contains("E001"), "El mensaje debe mencionar el id duplicado");

        // El registro original debe conservarse intacto
        Empleado original = service.buscarPorId("E001");
        assertEquals("juan.perez@empresa.com", original.getEmail(),
                "El registro original no debe ser sobrescrito");
    }

    @Test
    @DisplayName("registrar fuerza el estado ACTIVO aunque el input llegue con EN_VACACIONES")
    void registrarFuerzaEstadoActivoAunqueElInputTengaEnVacaciones() {
        Empleado conVacaciones = empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001");
        conVacaciones.setEstado(EstadoEmpleado.EN_VACACIONES);

        Empleado registrado = service.registrar(conVacaciones);

        assertEquals(EstadoEmpleado.ACTIVO, registrado.getEstado(),
                "En el Reto 2 el estado siempre debe forzarse a ACTIVO");
    }

    @Test
    @DisplayName("registrar con departamento inexistente lanza DepartamentoNoExisteException")
    void registrarDepartamentoInexistenteLanzaDepartamentoNoExiste() {
        when(departamentoClient.validar("NODEP")).thenReturn(false);

        Empleado empleado = empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001");
        empleado.setDepartamentoId("NODEP");

        DepartamentoNoExisteException ex = assertThrows(
                DepartamentoNoExisteException.class,
                () -> service.registrar(empleado),
                "Debe rechazarse un empleado cuyo departamento no existe"
        );
        assertEquals("El departamento con id 'NODEP' no existe", ex.getMessage());
        assertEquals(0, repository.count(), "No debe persistirse nada si el departamento no existe");
    }

    @Test
    @DisplayName("registrar con servicio de departamentos no disponible lanza DepartamentoNoDisponibleException")
    void registrarDepartamentoNoDisponibleLanzaDepartamentoNoDisponible() {
        when(departamentoClient.validar(anyString())).thenThrow(new DepartamentoNoDisponibleException());

        Empleado empleado = empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001");

        assertThrows(
                DepartamentoNoDisponibleException.class,
                () -> service.registrar(empleado),
                "Debe rechazarse el registro si el servicio de departamentos no está disponible"
        );
        assertEquals(0, repository.count(), "No debe persistirse nada si el servicio no está disponible");
    }

    @Test
    @DisplayName("buscarPorId devuelve el empleado existente")
    void buscarPorIdDevuelveEmpleadoExistente() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));

        Empleado encontrado = service.buscarPorId("E001");

        assertEquals("E001", encontrado.getId(), "Debe encontrarse el empleado con ese id");
    }

    @Test
    @DisplayName("buscarPorId con id inexistente lanza EmpleadoNotFoundException")
    void buscarPorIdInexistenteLanzaEmpleadoNotFoundException() {
        EmpleadoNotFoundException ex = assertThrows(
                EmpleadoNotFoundException.class,
                () -> service.buscarPorId("E999"),
                "Debe lanzarse la excepción cuando el id no existe"
        );
        assertEquals("El empleado con id E999 no existe", ex.getMessage());
    }

    @Test
    @DisplayName("listarTodos devuelve todos los empleados registrados")
    void listarTodosDevuelveTodosLosEmpleados() {
        service.registrar(empleadoValido("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        service.registrar(empleadoValido("E002", "maria.perez@empresa.com", "EMP-2026-002"));

        List<Empleado> todos = service.listarTodos();

        assertEquals(2, todos.size(), "Deben devolverse todos los empleados registrados");
    }

    @Test
    @DisplayName("registro concurrente con el mismo email permite un único éxito")
    @DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void registroConcurrenteMismoEmailPermiteUnSoloExito() throws Exception {
        int totalThreads = 8;
        ExecutorService executor = Executors.newFixedThreadPool(totalThreads);
        CountDownLatch listos = new CountDownLatch(totalThreads);
        CountDownLatch largada = new CountDownLatch(1);
        List<Future<ResultadoRegistro>> futuros = new ArrayList<>();

        try {
            for (int i = 1; i <= totalThreads; i++) {
                final int n = i;
                futuros.add(executor.submit(() -> {
                    listos.countDown();
                    // Barrera: todos parten a la vez para maximizar la contención sobre el check-then-act
                    largada.await(10, TimeUnit.SECONDS);
                    try {
                        service.registrar(empleadoValido("E-CONC-" + n, "concurrente@empresa.com", "EMP-CONC-" + n));
                        return ResultadoRegistro.EXITOSO;
                    } catch (EmpleadoDuplicadoException e) {
                        return ResultadoRegistro.DUPLICADO;
                    }
                }));
            }

            assertTrue(listos.await(10, TimeUnit.SECONDS),
                    "Los 8 threads deben quedar listos antes de la largada");

            largada.countDown();

            int exitosos = 0;
            int duplicados = 0;
            for (Future<ResultadoRegistro> futuro : futuros) {
                ResultadoRegistro resultado = futuro.get(10, TimeUnit.SECONDS);
                if (resultado == ResultadoRegistro.EXITOSO) {
                    exitosos++;
                } else {
                    duplicados++;
                }
            }

            assertEquals(1, exitosos,
                    "Solo un thread debe registrar el email con éxito");
            assertEquals(7, duplicados,
                    "Los 7 threads restantes deben recibir EmpleadoDuplicadoException");
        } finally {
            executor.shutdownNow();
        }
    }
}
