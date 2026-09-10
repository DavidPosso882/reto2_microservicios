package com.empresa.gestionempleados.exception;

/**
 * Se lanza cuando se intenta registrar un empleado con un email
 * o numeroEmpleado que ya existe en el sistema.
 */
public class EmpleadoDuplicadoException extends RuntimeException {

    public EmpleadoDuplicadoException(String mensaje) {
        super(mensaje);
    }
}
