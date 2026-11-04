package com.empresa.gestionempleados.controller;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.events.EventPublisher;
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

import java.time.LocalDate;
import java.time.ZoneOffset;

import static org.hamcrest.Matchers.hasSize;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Pruebas de integración de los endpoints nuevos del Reto 4:
 * PUT /empleados/{id} (actualización), DELETE /empleados/{id} (baja lógica)
 * y GET /empleados con filtros (estado, rango de fechaRetiro).
 *
 * El {@link EventPublisher} se mockea: los tests de controller no dependen
 * de un broker vivo (la política de publish-fail-safe se cubre en los tests
 * de servicio).
 */
@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD)
class EmpleadoControllerEventosIT {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private DepartamentoClient departamentoClient;

    @MockBean
    private EventPublisher eventPublisher;

    @BeforeEach
    void setUpDepartamentoStub() {
        when(departamentoClient.validar(anyString())).thenReturn(true);
    }

    private String empleadoJson(String id, String email, String numeroEmpleado) {
        return "{\"id\":\"" + id + "\",\"nombre\":\"Juan\",\"apellido\":\"Perez\","
                + "\"email\":\"" + email + "\",\"numeroEmpleado\":\"" + numeroEmpleado + "\","
                + "\"cargo\":\"Desarrollador Senior\",\"area\":\"Tecnologia\","
                + "\"departamentoId\":\"IT\",\"fechaIngreso\":\"2026-02-10\"}";
    }

    private void crearEmpleado(String id, String email, String numeroEmpleado) throws Exception {
        mockMvc.perform(post("/empleados")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(empleadoJson(id, email, numeroEmpleado)))
                .andExpect(status().isCreated());
    }

    @Test
    @DisplayName("PUT /empleados/{id} actualiza los campos enviados y devuelve 200")
    void putActualizaCamposYDevuelve200() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");

        String cambios = "{\"nombre\":\"Juan Carlos\",\"cargo\":\"Tech Lead\"}";

        mockMvc.perform(put("/empleados/E001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(cambios))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("E001"))
                .andExpect(jsonPath("$.nombre").value("Juan Carlos"))
                .andExpect(jsonPath("$.cargo").value("Tech Lead"))
                // los campos no enviados no deben cambiar
                .andExpect(jsonPath("$.apellido").value("Perez"));
    }

    @Test
    @DisplayName("PUT /empleados/{id} ignora los campos null (actualización parcial)")
    void putIgnoraCamposAusentes() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");

        mockMvc.perform(put("/empleados/E001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"nuevo@empresa.com\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("nuevo@empresa.com"))
                .andExpect(jsonPath("$.nombre").value("Juan"));
    }

    @Test
    @DisplayName("PUT /empleados/{id} con email de otro empleado devuelve 400 JSON")
    void putConEmailDuplicadoDevuelve400() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        crearEmpleado("E002", "maria.perez@empresa.com", "EMP-2026-002");

        mockMvc.perform(put("/empleados/E001")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"maria.perez@empresa.com\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.error")
                        .value("El email 'maria.perez@empresa.com' ya está registrado"));
    }

    @Test
    @DisplayName("PUT /empleados/{id} inexistente devuelve 404 JSON")
    void putInexistenteDevuelve404() throws Exception {
        mockMvc.perform(put("/empleados/E999")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"nombre\":\"Nadie\"}"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("El empleado con id E999 no existe"));
    }

    @Test
    @DisplayName("DELETE /empleados/{id} hace la baja lógica y devuelve 200 con estado RETIRADO y fechaRetiro")
    void deleteHaceBajaLogica() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");

        mockMvc.perform(delete("/empleados/E001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("E001"))
                .andExpect(jsonPath("$.estado").value("RETIRADO"))
                .andExpect(jsonPath("$.fechaRetiro").isNotEmpty());

        mockMvc.perform(get("/empleados/E001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.estado").value("RETIRADO"))
                .andExpect(jsonPath("$.fechaRetiro").isNotEmpty());
    }

    @Test
    @DisplayName("DELETE /empleados/{id} es idempotente: segunda llamada devuelve 200 sin cambiar fechaRetiro")
    void deleteEsIdempotente() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");

        String fechaPrimera = com.jayway.jsonpath.JsonPath.read(
                mockMvc.perform(delete("/empleados/E001"))
                        .andExpect(status().isOk())
                        .andReturn().getResponse().getContentAsString(), "$.fechaRetiro");

        mockMvc.perform(delete("/empleados/E001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.estado").value("RETIRADO"))
                .andExpect(jsonPath("$.fechaRetiro").value(fechaPrimera));
    }

    @Test
    @DisplayName("DELETE /empleados/{id} inexistente devuelve 404 JSON")
    void deleteInexistenteDevuelve404() throws Exception {
        mockMvc.perform(delete("/empleados/E999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.error").value("El empleado con id E999 no existe"));
    }

    @Test
    @DisplayName("GET /empleados?estado=RETIRADO devuelve solo los retirados")
    void getConFiltroEstadoRetirado() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        crearEmpleado("E002", "maria.perez@empresa.com", "EMP-2026-002");
        mockMvc.perform(delete("/empleados/E001")).andExpect(status().isOk());

        mockMvc.perform(get("/empleados").param("estado", "RETIRADO"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value("E001"));

        mockMvc.perform(get("/empleados").param("estado", "ACTIVO"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value("E002"));

        mockMvc.perform(get("/empleados"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(2)));
    }

    @Test
    @DisplayName("GET /empleados?estado=RETIRADO&desde&hasta filtra por el rango de fechaRetiro")
    void getConFiltroRangoFechaRetiro() throws Exception {
        crearEmpleado("E001", "juan.perez@empresa.com", "EMP-2026-001");
        mockMvc.perform(delete("/empleados/E001")).andExpect(status().isOk());

        LocalDate ayer = LocalDate.now(ZoneOffset.UTC).minusDays(1);
        LocalDate manana = LocalDate.now(ZoneOffset.UTC).plusDays(1);

        mockMvc.perform(get("/empleados")
                        .param("estado", "RETIRADO")
                        .param("desde", ayer.toString())
                        .param("hasta", manana.toString()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].id").value("E001"));

        mockMvc.perform(get("/empleados")
                        .param("estado", "RETIRADO")
                        .param("desde", manana.toString()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(0)));
    }
}
