package com.empresa.gestionempleados.config;

import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Configuración RabbitMQ del productor de eventos (Reto 4).
 *
 * <p>La conexión se configura con variables de entorno (convención de la
 * compose): {@code SPRING_RABBITMQ_HOST} (default {@code localhost}), puerto
 * 5672 y credenciales {@code SPRING_RABBITMQ_USERNAME} /
 * {@code SPRING_RABBITMQ_PASSWORD} (default {@code guest}).
 *
 * <p>El productor declara únicamente el exchange topic durable
 * {@code ecosistema.eventos}. Las colas las declara cada servicio consumer
 * (CATALOGO_EVENTOS.md, sección 2): aquí NO se declara colas.
 *
 * <p>El {@link RabbitTemplate} publica con {@link Jackson2JsonMessageConverter}:
 * los mensajes viajan como JSON con {@code content_type=application/json} según
 * el contrato del catálogo (sección 1). Sin converter, Spring AMQP serializa el
 * envelope con Java serialization ({@code application/x-java-serialized-object})
 * y los consumers los descartan como "malformed message".
 */
@Configuration
public class RabbitMQConfig {

    /** Exchange topic durable del ecosistema (routing key = type del evento). */
    public static final String EVENTOS_EXCHANGE = "ecosistema.eventos";

    public static final int AMQP_PORT = 5672;

    @Bean
    public ConnectionFactory connectionFactory() {
        CachingConnectionFactory factory = new CachingConnectionFactory(
                envOrDefault("SPRING_RABBITMQ_HOST", "localhost"), AMQP_PORT);
        factory.setUsername(envOrDefault("SPRING_RABBITMQ_USERNAME", "guest"));
        factory.setPassword(envOrDefault("SPRING_RABBITMQ_PASSWORD", "guest"));
        return factory;
    }

    @Bean
    public TopicExchange eventosExchange() {
        // Durable y no auto-delete: los mensajes sobreviven a reinicios del broker.
        return new TopicExchange(EVENTOS_EXCHANGE, true, false);
    }

    @Bean
    public MessageConverter jacksonJsonMessageConverter() {
        // JSON plano del catálogo: el envelope se serializa con Jackson y los
        // consumers (Go) lo parsean sin conocer clases Java.
        return new Jackson2JsonMessageConverter();
    }

    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setMessageConverter(jacksonJsonMessageConverter());
        return template;
    }

    private static String envOrDefault(String name, String defaultValue) {
        String value = System.getenv(name);
        return (value == null || value.isBlank()) ? defaultValue : value;
    }
}
