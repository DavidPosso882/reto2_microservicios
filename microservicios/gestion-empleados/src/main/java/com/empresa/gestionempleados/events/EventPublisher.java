package com.empresa.gestionempleados.events;

import java.time.Instant;
import java.util.Map;

/**
 * Puerto de publicación de eventos del ecosistema (Reto 4).
 *
 * <p>El servicio de empleados depende de esta interfaz, nunca del broker:
 * los tests unitarios inyectan un mock y publicar jamás debe romper el
 * flujo de negocio (el fallo de publicación se loguea, no revierte la BD).
 *
 * <p>El envelope (id UUID v4, type, version "1.0", occurredAt, producer,
 * data) lo construye la implementación, según CATALOGO_EVENTOS.md.
 */
public interface EventPublisher {

    /**
     * Publica un evento con el momento del hecho igual al momento actual.
     *
     * @param type nombre canónico del evento (routing key en AMQP)
     * @param data payload del evento (nunca null)
     */
    void publicar(String type, Map<String, Object> data);

    /**
     * Publica un evento indicando el momento del hecho de dominio.
     *
     * @param type       nombre canónico del evento (routing key en AMQP)
     * @param occurredAt momento del hecho de dominio (no el de publicación),
     *                   serializado ISO-8601 UTC en el envelope
     * @param data       payload del evento (nunca null)
     */
    void publicar(String type, Instant occurredAt, Map<String, Object> data);
}
