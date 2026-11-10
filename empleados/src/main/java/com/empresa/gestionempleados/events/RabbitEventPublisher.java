package com.empresa.gestionempleados.events;

import com.empresa.gestionempleados.config.RabbitMQConfig;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.slf4j.Logger;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
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

    /** Métrica de negocio (Proyecto Final): eventos publicados por tipo. */
    static final String METRICA_EVENTOS = "eventos_publicados";

    private final AmqpTemplate amqpTemplate;
    private final MeterRegistry meterRegistry;

    /** Uso en pruebas unitarias: métricas en un registro en memoria. */
    public RabbitEventPublisher(AmqpTemplate amqpTemplate) {
        this(amqpTemplate, new SimpleMeterRegistry());
    }

    /**
     * Constructor de Spring: usa el registro Prometheus de Actuator para que
     * {@code eventos_publicados_total{routing_key}} salga en /metrics.
     */
    @Autowired
    public RabbitEventPublisher(AmqpTemplate amqpTemplate, ObjectProvider<MeterRegistry> meterRegistry) {
        this(amqpTemplate, meterRegistry.getIfAvailable(SimpleMeterRegistry::new));
    }

    RabbitEventPublisher(AmqpTemplate amqpTemplate, MeterRegistry meterRegistry) {
        this.amqpTemplate = amqpTemplate;
        this.meterRegistry = meterRegistry;
        // Series en 0 desde el arranque: sin esto el primer evento de cada tipo
        // crea la serie ya en 1 y increase() de Prometheus no lo cuenta.
        for (String type : new String[] {
                EventTypes.EMPLEADO_CREADO, EventTypes.EMPLEADO_ACTUALIZADO, EventTypes.EMPLEADO_RETIRADO}) {
            contador(type);
        }
    }

    private Counter contador(String type) {
        return Counter.builder(METRICA_EVENTOS)
                .description("Eventos publicados al broker por routing key")
                .tag("routing_key", type)
                .register(meterRegistry);
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
        contador(type).increment();

        // Reto 8: log JSON con ids de dominio (sin datos sensibles).
        MDC.put("event.type", type);
        MDC.put("event.id", String.valueOf(envelope.get("id")));
        try {
            log.info("evento_publicado");
        } finally {
            MDC.remove("event.type");
            MDC.remove("event.id");
        }
    }
}
