package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.config.DepartamentoCircuitBreaker;
import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import com.empresa.gestionempleados.exception.DepartamentoNoExisteException;
import com.empresa.gestionempleados.exception.EmpleadoDuplicadoException;
import com.empresa.gestionempleados.exception.EmpleadoNotFoundException;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Servicio de negocio para la gestión de empleados.
 * Aplica las validaciones de unicidad y de departamento antes de persistir.
 *
 * <p>Reto 3: la validación contra departamentos está envuelta en un Circuit
 * Breaker. Cuando la dependencia lleva varios fallos seguidos, el circuito se
 * abre y el registro degrada a {@code PENDIENTE_VALIDACION} (fallback) en lugar
 * de agotar hilos esperando timeouts condenados a fallar. El 404 de negocio
 * (departamento inexistente) no abre el circuito: es una respuesta definitiva.
 */
@Service
public class EmpleadoService {

    private final EmpleadoRepository repository;
    private final DepartamentoClient departamentoClient;
    private final CircuitBreaker circuitoDepartamentos;

    public EmpleadoService(EmpleadoRepository repository, DepartamentoClient departamentoClient) {
        this.repository = repository;
        this.departamentoClient = departamentoClient;
        this.circuitoDepartamentos = DepartamentoCircuitBreaker.departamentos();
    }

    /**
     * Expone el circuito para observabilidad y para que los tests puedan
     * reiniciarlo sin HTTP. No es parte del contrato público del dominio.
     */
    CircuitBreaker getCircuitoDepartamentos() {
        return circuitoDepartamentos;
    }

    /**
     * Registra un nuevo empleado en el sistema.
     *
     * Método synchronized: dos requests concurrentes con el mismo id/email/numeroEmpleado
     * podrían ambos pasar las validaciones previas; al serializar el check-then-act solo
     * uno llega a insertar. Las pre-validaciones dan mensajes descriptivos, pero la
     * garantía REAL contra la carrera es la restricción UNIQUE a nivel de base de datos
     * (ver empleados/init.sql), que rechaza el segundo insert aunque escape a la validación
     * de la aplicación.
     *
     * Orden de validaciones:
     * 1. El id no debe estar previamente registrado.
     * 2. El email no debe estar previamente registrado.
     * 3. El numeroEmpleado no debe estar previamente registrado.
     * 4. El departamento debe existir (llamada al servicio de departamentos,
     *    protegida por el Circuit Breaker; en fallback se acepta como
     *    PENDIENTE_VALIDACION).
     * 5. El estado se fuerza a ACTIVO cuando la validación fue real.
     *
     * @param empleado datos del empleado a registrar
     * @return el empleado registrado (ACTIVO, o PENDIENTE_VALIDACION en fallback)
     * @throws EmpleadoDuplicadoException si el id, email o numeroEmpleado ya existen
     * @throws DepartamentoNoExisteException si el departamento no existe
     */
    public synchronized Empleado registrar(Empleado empleado) {
        if (repository.existsById(empleado.getId())) {
            throw new EmpleadoDuplicadoException(
                "El id '" + empleado.getId() + "' ya está registrado"
            );
        }

        if (repository.findByEmail(empleado.getEmail()).isPresent()) {
            throw new EmpleadoDuplicadoException(
                "El email '" + empleado.getEmail() + "' ya está registrado"
            );
        }

        if (repository.findByNumeroEmpleado(empleado.getNumeroEmpleado()).isPresent()) {
            throw new EmpleadoDuplicadoException(
                "El numeroEmpleado '" + empleado.getNumeroEmpleado() + "' ya está registrado"
            );
        }

        // Validación del departamento envuelta en el circuito. Solo la excepción
        // de indisponibilidad cuenta como fallo; el 404 llega como `false`.
        final boolean existe;
        try {
            existe = circuitoDepartamentos.executeSupplier(
                    () -> departamentoClient.validar(empleado.getDepartamentoId()));
        } catch (CallNotPermittedException e) {
            // Circuito OPEN: ya sabemos que está caído, ni se intenta la red.
            return guardarPendiente(empleado);
        } catch (DepartamentoNoDisponibleException e) {
            // Dependencia caída (tras los reintentos del cliente): degradar, no propagar.
            return guardarPendiente(empleado);
        }

        if (!existe) {
            throw new DepartamentoNoExisteException(empleado.getDepartamentoId());
        }

        // En el Reto 2 solo se maneja el estado ACTIVO.
        empleado.setEstado(EstadoEmpleado.ACTIVO);
        empleado.setMensaje(null);

        return repository.save(empleado);
    }

    /**
     * Revalida un empleado pendiente contra departamentos (reconciliación del
     * fallback, Reto 3). Idempotente: si ya está ACTIVO se devuelve tal cual.
     *
     * <p>A diferencia de {@link #registrar}, aquí no hay fallback: es una
     * operación explícita de reconciliación y sus fallos se reportan
     * (400 si el departamento no existe, 503 si sigue sin responder o el
     * circuito está abierto).
     *
     * @param id identificador del empleado
     * @return el empleado reconciliado
     */
    public synchronized Empleado revalidar(String id) {
        Empleado empleado = buscarPorId(id);
        if (empleado.getEstado() != EstadoEmpleado.PENDIENTE_VALIDACION) {
            return empleado;
        }
        if (!circuitoDepartamentos.executeSupplier(
                () -> departamentoClient.validar(empleado.getDepartamentoId()))) {
            throw new DepartamentoNoExisteException(empleado.getDepartamentoId());
        }
        empleado.setEstado(EstadoEmpleado.ACTIVO);
        empleado.setMensaje(null);
        return repository.save(empleado);
    }

    /**
     * Estado observable del circuito (para el endpoint
     * {@code GET /empleados/circuit/state} y la evidencia del reto).
     */
    public Map<String, Object> estadoCircuito() {
        CircuitBreaker.Metrics metricas = circuitoDepartamentos.getMetrics();
        Map<String, Object> estado = new LinkedHashMap<>();
        estado.put("nombre", circuitoDepartamentos.getName());
        estado.put("estado", circuitoDepartamentos.getState().name());
        estado.put("tasaFallosPorcentaje", metricas.getFailureRate());
        estado.put("llamadasExitosas", metricas.getNumberOfSuccessfulCalls());
        estado.put("llamadasFallidas", metricas.getNumberOfFailedCalls());
        estado.put("llamadasBloqueadas", metricas.getNumberOfNotPermittedCalls());
        return estado;
    }

    /**
     * Fallback de negocio: RRHH sigue trabajando aunque departamentos esté
     * caído. El registro queda marcado para reconciliación posterior en lugar
     * de inventar un departamento por defecto (eso nunca: inventa datos).
     *
     * El mensaje se fija DESPUÉS del save: con id asignado, el repositorio hace
     * merge y devuelve una copia gestionada donde los @Transient se pierden.
     */
    private Empleado guardarPendiente(Empleado empleado) {
        empleado.setEstado(EstadoEmpleado.PENDIENTE_VALIDACION);
        Empleado guardado = repository.save(empleado);
        guardado.setMensaje("Empleado registrado. Validación de departamento pendiente.");
        return guardado;
    }

    /**
     * Consulta un empleado por su identificador.
     *
     * @param id identificador del empleado
     * @return el empleado encontrado
     * @throws EmpleadoNotFoundException si no existe un empleado con ese id
     */
    public Empleado buscarPorId(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new EmpleadoNotFoundException(id));
    }

    /**
     * Consulta todos los empleados registrados.
     *
     * @return lista de todos los empleados
     */
    public List<Empleado> listarTodos() {
        return repository.findAll();
    }
}
