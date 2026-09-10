package com.empresa.gestionempleados.exception;

/**
 * Se lanza cuando se solicita un empleado que no existe en el sistema.
 */
public class EmpleadoNotFoundException extends RuntimeException {

    public EmpleadoNotFoundException(String id) {
        super("El empleado con id " + id + " no existe");
    }
}
