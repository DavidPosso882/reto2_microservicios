package com.empresa.gestionempleados.config;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

/**
 * Tests unitarios de la configuración RabbitMQ (Reto 4): el productor declara
 * el exchange topic durable del catálogo; las colas las declaran los consumers.
 */
class RabbitMQConfigTest {

    private final RabbitMQConfig config = new RabbitMQConfig();

    @Test
    @DisplayName("declara el exchange topic durable 'ecosistema.eventos' del catálogo")
    void declaraExchangeTopicDurable() {
        TopicExchange exchange = config.eventosExchange();

        assertEquals("ecosistema.ROTO-SIMULADO-P5", exchange.getName());
        assertEquals("topic", exchange.getType());
        assertTrue(exchange.isDurable(), "El exchange debe ser durable");
        assertFalse(exchange.isAutoDelete());
    }

    @Test
    @DisplayName("la conexión usa host/puerto/credenciales con defaults seguros")
    void conexionUsaValoresPorDefecto() {
        CachingConnectionFactory factory = (CachingConnectionFactory) config.connectionFactory();

        // Sin env vars en el entorno de tests: cae a los defaults del catálogo.
        assertEquals("localhost", factory.getHost());
        assertEquals(5672, factory.getPort());
        assertEquals("guest", factory.getUsername());
    }

    @Test
    @DisplayName("el RabbitTemplate usa Jackson2JsonMessageConverter: publica JSON, no serialización JDK")
    void rabbitTemplateUsaJacksonJsonConverter() {
        ConnectionFactory connectionFactory = mock(ConnectionFactory.class);

        RabbitTemplate template = config.rabbitTemplate(connectionFactory);

        assertTrue(template.getMessageConverter() instanceof Jackson2JsonMessageConverter,
                "El RabbitTemplate debe publicar con Jackson (content_type application/json)");
    }
}
