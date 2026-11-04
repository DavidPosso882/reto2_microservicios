package com.empresa.gestionempleados.controller;

import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
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
import java.util.Map;

/**
 * Controlador REST para la gestión de empleados.
 *
 * Endpoints expuestos (Reto 4: se suman actualización, baja lógica y filtros):
 *   POST /empleados       -> registrar un empleado (201 Created)
 *   GET  /empleados       -> listar empleados, con filtros opcionales estado/desde/hasta (200)
 *   GET  /empleados/{id}  -> consultar un empleado por id (200 / 404)
 *   PUT  /empleados/{id}  -> actualizar campos del empleado (200 / 400 / 404)
 *   DELETE /empleados/{id} -> baja lógica: estado RETIRADO + fechaRetiro (200 / 404)
 *   GET  /empleados/circuit/state -> estado observable del Circuit Breaker (200)
 *   POST /empleados/{id}/revalidar -> reconciliar un PENDIENTE_VALIDACION (200 / 400 / 404 / 503)
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
            @ApiResponse(responseCode = "201", description = "Empleado registrado correctamente (ACTIVO, o PENDIENTE_VALIDACION en fallback)"),
            @ApiResponse(responseCode = "400", description = "Datos inválidos, duplicados o departamento inexistente"),
    })
    public ResponseEntity<Empleado> registrar(@Valid @RequestBody Empleado empleado) {
        Empleado registrado = service.registrar(empleado);
        return ResponseEntity.status(HttpStatus.CREATED).body(registrado);
    }

    /**
     * Lista empleados, opcionalmente filtrados (Reto 4).
     *
     * GET /empleados
     * Params opcionales:
     *   estado -> filtra por igualdad exacta (ACTIVO, PENDIENTE_VALIDACION, EN_VACACIONES, RETIRADO)
     *   desde / hasta -> con estado=RETIRADO, rango inclusivo YYYY-MM-DD sobre fechaRetiro
     * Sin params devuelve todos los empleados (contrato del Reto 2 intacto).
     * Respuesta 200 OK: array JSON con los empleados que cumplen el filtro.
     */
    @GetMapping
    @Operation(summary = "Listar empleados",
            description = "Devuelve los empleados como un array JSON. Sin filtros devuelve todos; "
                    + "con estado filtra por igualdad exacta; con estado=RETIRADO acepta además "
                    + "desde y hasta (YYYY-MM-DD) para filtrar por rango inclusivo de fechaRetiro.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Lista de empleados (puede estar vacía)"),
            @ApiResponse(responseCode = "400", description = "Estado desconocido o formato de fecha inválido")
    })
    public List<Empleado> listar(@RequestParam(required = false) EstadoEmpleado estado,
                                 @RequestParam(required = false) String desde,
                                 @RequestParam(required = false) String hasta) {
        return service.listarConFiltros(estado, desde, hasta);
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

    /**
     * Estado observable del Circuit Breaker hacia departamentos.
     *
     * GET /empleados/circuit/state
     * Respuesta 200 OK: {"nombre","estado","tasaFallosPorcentaje",...}.
     * La ruta literal tiene prioridad sobre /{id}: un empleado con id
     * "circuit" quedaría ensombrecido (los ids reales son del tipo E001).
     */
    @GetMapping("/circuit/state")
    @Operation(summary = "Estado del Circuit Breaker",
            description = "Expone el estado observable del circuito hacia departamentos (CLOSED, OPEN o HALF_OPEN) con sus métricas.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Estado actual del circuito")
    })
    public Map<String, Object> estadoCircuito() {
        return service.estadoCircuito();
    }

    /**
     * Actualiza los campos editables de un empleado (Reto 4).
     *
     * PUT /empleados/{id}
     * Body: JSON parcial con los campos a modificar (los null se ignoran).
     * Respuesta 200 OK: empleado actualizado
     * Respuesta 400 Bad Request: email duplicado o departamento inexistente
     * Respuesta 404 Not Found: empleado no existe
     * Respuesta 503 Service Unavailable: departamentos no disponible
     */
    @PutMapping("/{id}")
    @Operation(summary = "Actualizar un empleado",
            description = "Actualiza nombre, apellido, email, cargo, area, departamentoId y fechaIngreso; "
                    + "los campos null se ignoran. Si el email o el departamento cambian se revalidan. "
                    + "Publica el evento empleado.actualizado con la foto completa.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Empleado actualizado"),
            @ApiResponse(responseCode = "400", description = "Email duplicado o departamento inexistente"),
            @ApiResponse(responseCode = "404", description = "Empleado no encontrado"),
            @ApiResponse(responseCode = "503", description = "Departamentos no disponible o circuito abierto")
    })
    public ResponseEntity<Empleado> actualizar(@PathVariable String id,
                                               @RequestBody Empleado datos) {
        return ResponseEntity.ok(service.actualizar(id, datos));
    }

    /**
     * Baja lógica de un empleado (Reto 4): el registro pasa a RETIRADO con
     * fechaRetiro y se conserva para auditoría; nunca se borra.
     *
     * DELETE /empleados/{id}
     * Respuesta 200 OK: empleado retirado (idempotente: si ya estaba RETIRADO
     * se devuelve tal cual)
     * Respuesta 404 Not Found: empleado no existe
     */
    @DeleteMapping("/{id}")
    @Operation(summary = "Retirar un empleado (baja lógica)",
            description = "Marca el empleado como RETIRADO con fechaRetiro en ISO-8601 UTC y publica "
                    + "el evento empleado.retirado. Idempotente si ya está retirado.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Empleado retirado"),
            @ApiResponse(responseCode = "404", description = "Empleado no encontrado")
    })
    public ResponseEntity<Empleado> retirar(@PathVariable String id) {
        return ResponseEntity.ok(service.retirar(id));
    }

    /**
     * Reconcilia un empleado aceptado con validación pendiente.
     *
     * POST /empleados/{id}/revalidar
     * Respuesta 200 OK: empleado reconciliado a ACTIVO (o tal cual si ya lo estaba).
     * Respuesta 400 Bad Request: el departamento sigue sin existir.
     * Respuesta 404 Not Found: el empleado no existe.
     * Respuesta 503 Service Unavailable: departamentos sigue caído o el circuito está abierto.
     */
    @PostMapping("/{id}/revalidar")
    @Operation(summary = "Revalidar un empleado pendiente",
            description = "Reconcilia un empleado en PENDIENTE_VALIDACION contra departamentos. Idempotente si ya está ACTIVO.")
    @ApiResponses(value = {
            @ApiResponse(responseCode = "200", description = "Empleado reconciliado"),
            @ApiResponse(responseCode = "400", description = "El departamento no existe"),
            @ApiResponse(responseCode = "404", description = "Empleado no encontrado"),
            @ApiResponse(responseCode = "503", description = "Departamentos no disponible o circuito abierto")
    })
    public ResponseEntity<Empleado> revalidar(@PathVariable String id) {
        return ResponseEntity.ok(service.revalidar(id));
    }
}
