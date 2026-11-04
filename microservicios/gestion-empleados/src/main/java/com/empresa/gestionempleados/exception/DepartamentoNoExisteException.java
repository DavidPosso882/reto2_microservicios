package com.empresa.gestionempleados.exception;

/**
 * Se lanza cuando el servicio de departamentos responde 404 para el departamento
 * solicitado, es decir, el departamento no existe.
 * Se traduce a una respuesta 400 con el mensaje descriptivo del reto.
 */
public class DepartamentoNoExisteException extends RuntimeException {

    public DepartamentoNoExisteException(String departamentoId) {
        super("El departamento con id '" + departamentoId + "' no existe");
    }
}
