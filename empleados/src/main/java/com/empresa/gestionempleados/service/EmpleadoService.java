package com.empresa.gestionempleados.service;

import com.empresa.gestionempleados.client.DepartamentoClient;
import com.empresa.gestionempleados.exception.DepartamentoNoExisteException;
import com.empresa.gestionempleados.exception.EmpleadoDuplicadoException;
import com.empresa.gestionempleados.exception.EmpleadoNotFoundException;
import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import com.empresa.gestionempleados.repository.EmpleadoRepository;
import org.springframework.stereotype.Service;

import java.util.List;

/**
 * Servicio de negocio para la gestión de empleados.
 * Aplica las validaciones de unicidad y de departamento antes de persistir.
 */
@Service
public class EmpleadoService {

    private final EmpleadoRepository repository;
    private final DepartamentoClient departamentoClient;

    public EmpleadoService(EmpleadoRepository repository, DepartamentoClient departamentoClient) {
        this.repository = repository;
        this.departamentoClient = departamentoClient;
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
     * 4. El departamento debe existir (llamada al servicio de departamentos).
     * 5. El estado se fuerza a ACTIVO en el Reto 2.
     *
     * @param empleado datos del empleado a registrar
     * @return el empleado registrado
     * @throws EmpleadoDuplicadoException si el id, email o numeroEmpleado ya existen
     * @throws DepartamentoNoExisteException si el departamento no existe
     * @throws com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException
     *         si el servicio de departamentos no responde tras los reintentos
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

        // Validación del departamento: la llamada HTTP es responsabilidad de DepartamentoClient.
        if (!departamentoClient.validar(empleado.getDepartamentoId())) {
            throw new DepartamentoNoExisteException(empleado.getDepartamentoId());
        }

        // En el Reto 2 solo se maneja el estado ACTIVO.
        empleado.setEstado(EstadoEmpleado.ACTIVO);

        return repository.save(empleado);
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
