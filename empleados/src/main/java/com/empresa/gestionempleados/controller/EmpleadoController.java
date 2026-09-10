package com.empresa.gestionempleados.controller;

import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.service.EmpleadoService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Controlador REST para la gestión de empleados.
 *
 * Endpoints expuestos (Reto 2):
 *   POST /empleados       -> registrar un empleado (201 Created)
 *   GET  /empleados       -> listar todos los empleados (200)
 *   GET  /empleados/{id}  -> consultar un empleado por id (200 / 404)
 */
@RestController
@RequestMapping("/empleados")
@Tag(name = "Empleados", description = "Operaciones de registro y consulta de empleados")
public class EmpleadoController {

    private final EmpleadoService service;

    public EmpleadoController(EmpleadoService service) {
        this.service = service;
    }

    /**
     * Registra un nuevo empleado.
     *
     * POST /empleados
     * Body: JSON con los campos del modelo canónico
     * Respuesta 201 Created: empleado registrado
     * Respuesta 400 Bad Request: validación fallida (duplicados, campos inválidos o departamento inexistente)
     * Respuesta 503 Service Unavailable: servicio de departamentos no disponible
     */
    @PostMapping
    @Operation(summary = "Registrar un empleado",
            description = "Registra un nuevo empleado. El estado se fuerza a ACTIVO y el departamento se valida contra el servicio de departamentos. Respuesta 201 Created (antes era 200 en el Reto 1).")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "201", description = "Empleado registrado correctamente"),
            @ApiResponse(responseCode = "400", description = "Datos inválidos, duplicados o departamento inexistente"),
            @ApiResponse(responseCode = "503", description = "Servicio de departamentos no disponible")
    })
    public ResponseEntity<Empleado> registrar(@Valid @RequestBody Empleado empleado) {
        Empleado registrado = service.registrar(empleado);
        return ResponseEntity.status(HttpStatus.CREATED).body(registrado);
    }

    /**
     * Lista todos los empleados registrados.
     *
     * GET /empleados
     * Respuesta 200 OK: array JSON con los empleados (vacío si no hay ninguno)
     */
    @GetMapping
    @Operation(summary = "Listar empleados", description = "Devuelve todos los empleados registrados como un array JSON.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Lista de empleados (puede estar vacía)")
    })
    public List<Empleado> listar() {
        return service.listarTodos();
    }

    /**
     * Consulta un empleado por su id.
     *
     * GET /empleados/{id}
     * Respuesta 200 OK: datos del empleado
     * Respuesta 404 Not Found: empleado no existe
     */
    @GetMapping("/{id}")
    @Operation(summary = "Consultar un empleado por id", description = "Devuelve los datos del empleado cuyo id coincide.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Datos del empleado"),
            @ApiResponse(responseCode = "404", description = "Empleado no encontrado")
    })
    public ResponseEntity<Empleado> buscarPorId(@PathVariable String id) {
        Empleado empleado = service.buscarPorId(id);
        return ResponseEntity.ok(empleado);
    }
}
