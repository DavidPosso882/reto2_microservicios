package com.empresa.gestionempleados.events;

import com.empresa.gestionempleados.config.RabbitMQConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Publicación AMQP de los eventos del ecosistema (Reto 4).
 *
 * <p>Publica al exchange topic durable {@code ecosistema.eventos} con
 * routing key = {@code type} (CATALOGO_EVENTOS.md, sección 2). Las colas
 * las declaran los consumers; este productor no declara ninguna.
 *
 * <p>El envelope se construye según la sección 1 del catálogo:
 * {@code id} UUID v4 (clave de deduplicación), {@code version} "1.0",
 * {@code occurredAt} ISO-8601 UTC del hecho de dominio y
 * {@code producer} "empleados-service".
 */
@Component
public class RabbitEventPublisher implements EventPublisher {

    private static final Logger log = LoggerFactory.getLogger(RabbitEventPublisher.class);

    static final String VERSION = "1.0";
    static final String PRODUCER = "empleados-service";

    private final AmqpTemplate amqpTemplate;

    public RabbitEventPublisher(AmqpTemplate amqpTemplate) {
        this.amqpTemplate = amqpTemplate;
    }

    @Override
    public void publicar(String type, Map<String, Object> data) {
        publicar(type, Instant.now(), data);
    }

    @Override
    public void publicar(String type, Instant occurredAt, Map<String, Object> data) {
        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("id", UUID.randomUUID().toString());
        envelope.put("type", type);
        envelope.put("version", VERSION);
        envelope.put("occurredAt", DateTimeFormatter.ISO_INSTANT.format(occurredAt));
        envelope.put("producer", PRODUCER);
        envelope.put("data", data != null ? data : new LinkedHashMap<>());

        amqpTemplate.convertAndSend(RabbitMQConfig.EVENTOS_EXCHANGE, type, envelope);
        log.debug("Evento '{}' publicado con id {}", type, envelope.get("id"));
    }
}
