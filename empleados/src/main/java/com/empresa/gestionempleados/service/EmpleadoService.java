package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.config.DepartamentoCircuitBreaker;
import com.empresa.gestionempleados.events.EventPublisher;
import com.empresa.gestionempleados.events.EventTypes;
import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import com.empresa.gestionempleados.exception.DepartamentoNoExisteException;
import com.empresa.gestionempleados.exception.EmpleadoDuplicadoException;
import com.empresa.gestionempleados.exception.EmpleadoNotFoundException;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.format.DateTimeFormatter;
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
 *
 * <p>Reto 4: tras cada hecho de dominio exitoso (registro, actualización,
 * baja lógica) se publica el evento correspondiente del catálogo del
 * ecosistema (CATALOGO_EVENTOS.md). El servicio depende de la interfaz
 * {@link EventPublisher}; publicar es best-effort: un fallo se loguea y
 * nunca revierte la base de datos.
 */
@Service
public class EmpleadoService {

    private static final Logger log = LoggerFactory.getLogger(EmpleadoService.class);

    private final EmpleadoRepository repository;
    private final DepartamentoClient departamentoClient;
    private final CircuitBreaker circuitoDepartamentos;
    private final EventPublisher eventPublisher;

    public EmpleadoService(EmpleadoRepository repository,
                           DepartamentoClient departamentoClient,
                           EventPublisher eventPublisher) {
        this.repository = repository;
        this.departamentoClient = departamentoClient;
        this.circuitoDepartamentos = DepartamentoCircuitBreaker.departamentos();
        this.eventPublisher = eventPublisher;
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

        Empleado guardado = repository.save(empleado);
        publicarSeguro(EventTypes.EMPLEADO_CREADO, Instant.now(), fotoCompleta(guardado));
        return guardado;
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
        // Reto 4: el evento se publica también en fallback, con el estado real.
        publicarSeguro(EventTypes.EMPLEADO_CREADO, Instant.now(), fotoCompleta(guardado));
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

    /**
     * Actualiza los campos editables de un empleado (Reto 4). Los campos
     * null del cuerpo se ignoran (actualización parcial): nombre, apellido,
     * email, cargo, area, departamentoId y fechaIngreso.
     *
     * Reglas:
     * 1. Si el email cambia, se revalida su unicidad (400 si ya está tomado).
     * 2. Si el departamentoId cambia, se revalida contra departamentos:
     *    404 de negocio si no existe, y la indisponibilidad se propaga como
     *    DepartamentoNoDisponibleException (503 en el controller) — a
     *    diferencia de {@link #registrar}, aquí NO hay fallback.
     * 3. Tras el save exitoso se publica {@code empleado.actualizado} con la
     *    foto completa del empleado ya actualizado (CATALOGO_EVENTOS.md 3.2).
     *    Un fallo de publicación se loguea y NO revierte la BD.
     *
     * @param id    identificador del empleado a actualizar
     * @param datos campos a modificar (los null se ignoran)
     * @return el empleado actualizado
     * @throws EmpleadoNotFoundException          si el empleado no existe
     * @throws EmpleadoDuplicadoException         si el email nuevo ya está registrado
     * @throws DepartamentoNoExisteException      si el departamento nuevo no existe
     * @throws DepartamentoNoDisponibleException  si departamentos no responde o el circuito está abierto
     */
    public synchronized Empleado actualizar(String id, Empleado datos) {
        Empleado empleado = buscarPorId(id);

        boolean emailCambia = datos.getEmail() != null && !datos.getEmail().equals(empleado.getEmail());
        if (emailCambia && repository.findByEmail(datos.getEmail()).isPresent()) {
            throw new EmpleadoDuplicadoException(
                    "El email '" + datos.getEmail() + "' ya está registrado");
        }

        boolean departamentoCambia = datos.getDepartamentoId() != null
                && !datos.getDepartamentoId().equals(empleado.getDepartamentoId());
        if (departamentoCambia) {
            final boolean existe;
            try {
                existe = circuitoDepartamentos.executeSupplier(
                        () -> departamentoClient.validar(datos.getDepartamentoId()));
            } catch (CallNotPermittedException e) {
                // Circuito OPEN: la indisponibilidad se propaga, no hay fallback aquí.
                throw new DepartamentoNoDisponibleException();
            }
            if (!existe) {
                throw new DepartamentoNoExisteException(datos.getDepartamentoId());
            }
        }

        if (datos.getNombre() != null) {
            empleado.setNombre(datos.getNombre());
        }
        if (datos.getApellido() != null) {
            empleado.setApellido(datos.getApellido());
        }
        if (datos.getEmail() != null) {
            empleado.setEmail(datos.getEmail());
        }
        if (datos.getCargo() != null) {
            empleado.setCargo(datos.getCargo());
        }
        if (datos.getArea() != null) {
            empleado.setArea(datos.getArea());
        }
        if (datos.getDepartamentoId() != null) {
            empleado.setDepartamentoId(datos.getDepartamentoId());
        }
        if (datos.getFechaIngreso() != null) {
            empleado.setFechaIngreso(datos.getFechaIngreso());
        }

        Empleado guardado = repository.save(empleado);
        publicarSeguro(EventTypes.EMPLEADO_ACTUALIZADO, Instant.now(), fotoCompleta(guardado));
        return guardado;
    }

    /**
     * Baja lógica de un empleado (Reto 4): {@code estado = RETIRADO} más
     * {@code fechaRetiro} en ISO-8601 UTC. El registro se conserva para
     * auditoría; nunca se borra.
     *
     * <p>Idempotente: si el empleado ya está RETIRADO se devuelve tal cual,
     * sin volver a publicar el evento. Tras el save exitoso se publica
     * {@code empleado.retirado} con {@code occurredAt = fechaRetiro}
     * (CATALOGO_EVENTOS.md 3.3). Un fallo de publicación se loguea y NO
     * revierte la baja.
     *
     * @param id identificador del empleado a retirar
     * @return el empleado retirado
     * @throws EmpleadoNotFoundException si el empleado no existe
     */
    public synchronized Empleado retirar(String id) {
        Empleado empleado = buscarPorId(id);
        if (empleado.getEstado() == EstadoEmpleado.RETIRADO) {
            return empleado;
        }

        String fechaRetiro = DateTimeFormatter.ISO_INSTANT.format(Instant.now());
        empleado.setEstado(EstadoEmpleado.RETIRADO);
        empleado.setFechaRetiro(fechaRetiro);

        Empleado guardado = repository.save(empleado);

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", guardado.getId());
        data.put("nombre", guardado.getNombre());
        data.put("apellido", guardado.getApellido());
        data.put("email", guardado.getEmail());
        data.put("estado", guardado.getEstado().name());
        data.put("fechaRetiro", guardado.getFechaRetiro());

        // El occurredAt del retiro es la fechaRetiro (el hecho de dominio).
        publicarSeguro(EventTypes.EMPLEADO_RETIRADO, Instant.parse(guardado.getFechaRetiro()), data);
        return guardado;
    }

    /**
     * Lista empleados con filtros opcionales (Reto 4).
     *
     * <ul>
     *   <li>{@code estado == null}: devuelve todos los empleados.</li>
     *   <li>{@code estado == RETIRADO}: solo retirados; si {@code desde} o
     *       {@code hasta} (formato YYYY-MM-DD) vienen, filtra por el día de
     *       {@code fechaRetiro} en rango inclusivo. Comparar por prefijo de
     *       fecha funciona porque ISO-8601 UTC es lexicográficamente ordenable.</li>
     *   <li>Cualquier otro estado: filtrado por igualdad exacta.</li>
     * </ul>
     *
     * @param estado estado a filtrar (opcional)
     * @param desde  fecha de inicio del rango de fechaRetiro (opcional, YYYY-MM-DD)
     * @param hasta  fecha de fin del rango de fechaRetiro (opcional, YYYY-MM-DD)
     * @return los empleados que cumplen los filtros
     */
    public List<Empleado> listarConFiltros(EstadoEmpleado estado, String desde, String hasta) {
        List<Empleado> base = repository.findAll();
        if (estado == null) {
            return base;
        }

        var filtrados = base.stream()
                .filter(e -> e.getEstado() == estado);

        if (estado == EstadoEmpleado.RETIRADO && (desde != null || hasta != null)) {
            filtrados = filtrados.filter(e -> fechaRetiroEnRango(e, desde, hasta));
        }
        return filtrados.toList();
    }

    /**
     * Rango inclusivo sobre el prefijo de fecha (YYYY-MM-DD) de fechaRetiro.
     */
    private boolean fechaRetiroEnRango(Empleado empleado, String desde, String hasta) {
        String fechaRetiro = empleado.getFechaRetiro();
        if (fechaRetiro == null || fechaRetiro.length() < 10) {
            return false;
        }
        String fecha = fechaRetiro.substring(0, 10);
        if (desde != null && fecha.compareTo(prefijoFecha(desde)) < 0) {
            return false;
        }
        if (hasta != null && fecha.compareTo(prefijoFecha(hasta)) > 0) {
            return false;
        }
        return true;
    }

    private String prefijoFecha(String fecha) {
        return fecha.length() >= 10 ? fecha.substring(0, 10) : fecha;
    }

    /**
     * Foto completa del empleado para los eventos creado/actualizado
     * (CATALOGO_EVENTOS.md 3.1/3.2): mismo modelo canónico del REST.
     */
    private Map<String, Object> fotoCompleta(Empleado empleado) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", empleado.getId());
        data.put("nombre", empleado.getNombre());
        data.put("apellido", empleado.getApellido());
        data.put("email", empleado.getEmail());
        data.put("numeroEmpleado", empleado.getNumeroEmpleado());
        data.put("cargo", empleado.getCargo());
        data.put("area", empleado.getArea());
        data.put("departamentoId", empleado.getDepartamentoId());
        data.put("fechaIngreso", empleado.getFechaIngreso());
        data.put("estado", empleado.getEstado().name());
        return data;
    }

    /**
     * Publica el evento aislando al flujo de negocio del broker: cualquier
     * fallo de publicación se loguea y se continúa. La garantía de coherencia
     * es el save (la BD manda); el evento es best-effort.
     */
    private void publicarSeguro(String type, Instant occurredAt, Map<String, Object> data) {
        try {
            eventPublisher.publicar(type, occurredAt, data);
        } catch (Exception e) {
            log.error("No se pudo publicar el evento '{}' para el empleado {}: {}",
                    type, data.get("id"), e.getMessage());
        }
    }
}
