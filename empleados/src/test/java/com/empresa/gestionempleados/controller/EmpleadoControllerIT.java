package com.empresa.gestionempleados.controller;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Pruebas de integración del controlador REST con MockMvc.
 * Todos los errores se devuelven en JSON: {"status":400,"error":"..."}.
 *
 * La llamada al servicio de departamentos se stubea con {@link MockBean}:
 * no hay dependencia viva en los tests.
 */
@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD)
class EmpleadoControllerIT {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private DepartamentoClient departamentoClient;

    @BeforeEach
    void setUpDepartamentoStub() {
        // Por defecto el departamento "IT" existe; cada test concreto puede sobrescribirlo.
        when(departamentoClient.validar(anyString())).thenReturn(true);
    }

    /** Fixture base de un empleado válido (el estado se fuerza a ACTIVO). */
    private static final String EMPLEADO_VALIDO =
            "{\"id\":\"E001\",\"nombre\":\"Juan\",\"apellido\":\"Perez\","
            + "\"email\":\"juan.perez@empresa.com\",\"numeroEmpleado\":\"EMP-2026-001\","
            + "\"cargo\":\"Desarrollador Senior\",\"area\":\"Tecnologia\","
            + "\"departamentoId\":\"IT\",\"fechaIngreso\":\"2026-02-10\"}";

    /**
     * Construye el JSON de un empleado con los campos dados.
     */
    private String empleadoJson(String id, String email, String numeroEmpleado) {
        return "{\"id\":\"" + id + "\",\"nombre\":\"Juan\",\"apellido\":\"Perez\","
                + "\"email\":\"" + email + "\",\"numeroEmpleado\":\"" + numeroEmpleado + "\","
                + "\"cargo\":\"Desarrollador Senior\",\"area\":\"Tecnologia\","
                + "\"departamentoId\":\"IT\",\"fechaIngreso\":\"2026-02-10\"}";
    }

    @Test
    @DisplayName("POST /empleados válido devuelve 201 Created con estado ACTIVO")
    void postEmpleadoValidoDevuelve201YEstadoActivo() throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("E001"))
                .andExpect(jsonPath("$.estado").value("ACTIVO"));
    }

    @Test
    @DisplayName("POST /empleados con email duplicado devuelve 400 JSON")
    void postEmailDuplicadoDevuelve400() throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(empleadoJson("E002", "juan.perez@empresa.com", "EMP-2026-002")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error").value("El email 'juan.perez@empresa.com' ya está registrado"));
    }

    @Test
    @DisplayName("POST /empleados con numeroEmpleado duplicado devuelve 400 JSON")
    void postNumeroEmpleadoDuplicadoDevuelve400() throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(empleadoJson("E002", "otro.perez@empresa.com", "EMP-2026-001")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error").value("El numeroEmpleado 'EMP-2026-001' ya está registrado"));
    }

    @Test
    @DisplayName("POST /empleados con id duplicado devuelve 400 JSON sin sobrescribir (B3)")
    void postIdDuplicadoDevuelve400() throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(empleadoJson("E001", "otro.perez@empresa.com", "EMP-2026-002")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error").value("El id 'E001' ya está registrado"));

        // El registro original debe conservarse intacto
        mockMvc.perform(get("/empleados/E001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("juan.perez@empresa.com"));
    }

    @Test
    @DisplayName("POST /empleados sin campo nombre devuelve 400 JSON")
    void postSinCampoNombreDevuelve400() throws Exception {
        String sinNombre = "{\"id\":\"E003\",\"apellido\":\"Perez\","
                + "\"email\":\"sin.nombre@empresa.com\",\"numeroEmpleado\":\"EMP-2026-003\","
                + "\"cargo\":\"Desarrollador\",\"area\":\"Tecnologia\","
                + "\"departamentoId\":\"IT\",\"fechaIngreso\":\"2026-02-10\"}";

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(sinNombre))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error", containsString("nombre")));
    }

    @Test
    @DisplayName("POST /empleados con fechaIngreso en formato DD-MM-YYYY devuelve 400 JSON")
    void postFechaDeIngresoInvalidaDevuelve400() throws Exception {
        String fechaInvalida = "{\"id\":\"E006\",\"nombre\":\"Juan\",\"apellido\":\"Perez\","
                + "\"email\":\"fecha.invalida@empresa.com\",\"numeroEmpleado\":\"EMP-2026-006\","
                + "\"cargo\":\"Desarrollador\",\"area\":\"Tecnologia\","
                + "\"departamentoId\":\"IT\",\"fechaIngreso\":\"10-02-2026\"}";

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(fechaInvalida))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error", containsString("fechaIngreso")));
    }

    @Test
    @DisplayName("POST /empleados con estado inválido devuelve 400 JSON (B2)")
    void postEstadoInvalidoDevuelve400() throws Exception {
        String estadoInvalido = "{\"id\":\"E004\",\"nombre\":\"Juan\",\"apellido\":\"Perez\","
                + "\"email\":\"estado.invalido@empresa.com\",\"numeroEmpleado\":\"EMP-2026-004\","
                + "\"cargo\":\"Desarrollador\",\"area\":\"Tecnologia\","
                + "\"departamentoId\":\"IT\",\"fechaIngreso\":\"2026-02-10\","
                + "\"estado\":\"INVALIDO\"}";

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(estadoInvalido))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error").value("Datos inválidos: el cuerpo de la solicitud no es un JSON válido o contiene un estado desconocido"));
    }

    @Test
    @DisplayName("POST /empleados con JSON malformado devuelve 400 JSON (B2)")
    void postJsonMalformadoDevuelve400() throws Exception {
        String jsonMalformado = "{\"id\":\"E005\",\"nombre\":\"Juan\"";

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(jsonMalformado))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error").value("Datos inválidos: el cuerpo de la solicitud no es un JSON válido o contiene un estado desconocido"));
    }

    @Test
    @DisplayName("POST /empleados con departamento inexistente devuelve 400 JSON (Reto 2)")
    void postDepartamentoInexistenteDevuelve400() throws Exception {
        when(departamentoClient.validar("NODEP")).thenReturn(false);

        String sinDepartamento = "{\"id\":\"E007\",\"nombre\":\"Juan\",\"apellido\":\"Perez\","
                + "\"email\":\"dep.inexistente@empresa.com\",\"numeroEmpleado\":\"EMP-2026-007\","
                + "\"cargo\":\"Desarrollador\",\"area\":\"Tecnologia\","
                + "\"departamentoId\":\"NODEP\",\"fechaIngreso\":\"2026-02-10\"}";

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(sinDepartamento))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error").value("El departamento con id 'NODEP' no existe"));
    }

    @Test
    @DisplayName("POST /empleados con servicio de departamentos no disponible devuelve 503 JSON (Reto 2)")
    void postDepartamentoNoDisponibleDevuelve503() throws Exception {
        when(departamentoClient.validar(anyString())).thenThrow(new DepartamentoNoDisponibleException());

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.status").value(503))
                .andExpect(jsonPath("$.error").value("El servicio de departamentos no está disponible en este momento, intente más tarde"));
    }

    @Test
    @DisplayName("GET /empleados/{id} existente devuelve 200")
    void getEmpleadoExistenteDevuelve200() throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isCreated());

        mockMvc.perform(get("/empleados/E001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("E001"))
                .andExpect(jsonPath("$.nombre").value("Juan"));
    }

    @Test
    @DisplayName("GET /empleados/E999 devuelve 404 JSON con el mensaje del reto")
    void getEmpleadoInexistenteDevuelve404() throws Exception {
        mockMvc.perform(get("/empleados/E999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("El empleado con id E999 no existe"));
    }

    @Test
    @DisplayName("GET /empleados (raíz) devuelve 200 con lista vacía (Reto 2)")
    void getEmpleadosRaizDevuelve200YListaVacia() throws Exception {
        mockMvc.perform(get("/empleados"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));
    }

    @Test
    @DisplayName("GET /empleados (raíz) devuelve 200 con todos los empleados registrados (Reto 2)")
    void getEmpleadosRaizDevuelve200ConEmpleados() throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isCreated());

        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(empleadoJson("E002", "maria.perez@empresa.com", "EMP-2026-002")))
                .andExpect(status().isCreated());

        mockMvc.perform(get("/empleados"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)))
                .andExpect(jsonPath("$[0].id").value("E001"))
                .andExpect(jsonPath("$[1].id").value("E002"));
    }

    @Test
    @DisplayName("GET de ruta no definida devuelve 404 JSON 'Recurso no encontrado'")
    void getRutaNoDefinidaDevuelve404() throws Exception {
        mockMvc.perform(get("/otra-ruta"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("Recurso no encontrado"));
    }

    @Test
    @DisplayName("DELETE /empleados devuelve 404 JSON 'Recurso no encontrado' (B1)")
    void deleteEmpleadosDevuelve404() throws Exception {
        mockMvc.perform(delete("/empleados"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("Recurso no encontrado"));
    }

    @Test
    @DisplayName("POST /empleados/E001 (método no mapeado) devuelve 404 JSON 'Recurso no encontrado' (B1)")
    void postMetodoNoMapeadoEnSubrutaDevuelve404() throws Exception {
        mockMvc.perform(post("/empleados/E001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(EMPLEADO_VALIDO))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("Recurso no encontrado"));
    }
}
