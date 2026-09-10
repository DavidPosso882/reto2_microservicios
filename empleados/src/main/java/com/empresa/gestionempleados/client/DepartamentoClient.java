package com.empresa.gestionempleados.client;

/**
 * Cliente del servicio de departamentos (Reto 2).
 *
 * Valida que un departamento exista antes de registrar un empleado.
 * La implementación concreta hace una llamada HTTP con timeout y reintentos;
 * en los tests se sustituye por un stub (no hay dependencia viva en las pruebas).
 */
public interface DepartamentoClient {

    /**
     * Verifica si existe un departamento con el id dado.
     *
     * @param departamentoId id del departamento a validar
     * @return true si el departamento existe (2xx), false si no existe (404)
     * @throws com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException
     *         si se agotan los reintentos sin respuesta concluyente
     */
    boolean validar(String departamentoId);
}
