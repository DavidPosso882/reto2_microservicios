package com.empresa.gestionempleados.repository;

import com.empresa.gestionempleados.model.Empleado;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

/**
 * Repositorio JPA para la entidad {@link Empleado}.
 *
 * Desde el Reto 2 la persistencia es con Spring Data JPA sobre PostgreSQL.
 * La garantía real de unicidad de email y numeroEmpleado la aportan las
 * restricciones UNIQUE definidas a nivel de base de datos (ver empleados/init.sql);
 * los finders de abajo se usan para detectar duplicados con mensajes descriptivos
 * antes de insertar.
 */
@Repository
public interface EmpleadoRepository extends JpaRepository<Empleado, String> {

    /**
     * Busca un empleado por su email (único).
     */
    Optional<Empleado> findByEmail(String email);

    /**
     * Busca un empleado por su numeroEmpleado (único).
     */
    Optional<Empleado> findByNumeroEmpleado(String numeroEmpleado);
}
