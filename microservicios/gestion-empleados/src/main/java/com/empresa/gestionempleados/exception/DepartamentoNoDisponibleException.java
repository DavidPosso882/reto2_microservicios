package com.empresa.gestionempleados.exception;

/**
 * Se lanza cuando el servicio de departamentos no responde de forma concluyente
 * tras agotar los reintentos (timeout de red o errores 5xx persistentes).
 * Se traduce a una respuesta 503. La operación se rechaza: nunca se acepta como pendiente.
 */
public class DepartamentoNoDisponibleException extends RuntimeException {

    public DepartamentoNoDisponibleException() {
        super("El servicio de departamentos no está disponible en este momento, intente más tarde");
    }
}
