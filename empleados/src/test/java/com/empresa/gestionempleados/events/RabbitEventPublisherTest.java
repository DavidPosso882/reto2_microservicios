package com.empresa.gestionempleados.events;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.empresa.gestionempleados.config.RabbitMQConfig;
import com.rabbitmq.client.AMQP;
import com.rabbitmq.client.Channel;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Tests unitarios del publisher AMQP contra el catálogo normativo
 * (CATALOGO_EVENTOS.md, secciones 1, 2 y 3): envelope, exchange y routing key.
 * El {@link AmqpTemplate} se mockea: no hay broker vivo en los tests.
 */
class RabbitEventPublisherTest {

    private final AmqpTemplate amqp = mock(AmqpTemplate.class);
    private final RabbitEventPublisher publisher = new RabbitEventPublisher(amqp);

    @Test
    @DisplayName("publica al exchange ecosistema.eventos con routing key = type")
    void publicaAlExchangeConRoutingKeyIgualAlType() {
        Map<String, Object> data = Map.of("id", "E001", "estado", "ACTIVO");

        publisher.publicar("empleado.creado", Instant.parse("2026-09-21T14:30:00Z"), data);

        ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
        verify(amqp).convertAndSend(eq("ecosistema.eventos"), eq("empleado.creado"), captor.capture());
        @SuppressWarnings("unchecked")
        Map<String, Object> envelope = (Map<String, Object>) captor.getValue();

        assertEquals("empleado.creado", envelope.get("type"));
        assertEquals("1.0", envelope.get("version"));
        assertEquals("2026-09-21T14:30:00Z", envelope.get("occurredAt"));
        assertEquals("empleados-service", envelope.get("producer"));
        assertEquals(data, envelope.get("data"));
        UUID id = UUID.fromString(envelope.get("id").toString());
        assertEquals(4, id.version(), "El id del envelope debe ser UUID v4");
    }

    @Test
    @DisplayName("cada publicación genera un id de deduplicación distinto")
    void cadaPublicacionGeneraIdDistinto() {
        Map<String, Object> data = Map.of("id", "E001");

        publisher.publicar("empleado.creado", Instant.now(), data);
        publisher.publicar("empleado.creado", Instant.now(), data);

        ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
        verify(amqp, org.mockito.Mockito.times(2))
                .convertAndSend(eq("ecosistema.eventos"), eq("empleado.creado"), captor.capture());
        Object primerId = ((Map<?, ?>) captor.getAllValues().get(0)).get("id");
        Object segundoId = ((Map<?, ?>) captor.getAllValues().get(1)).get("id");
        assertTrue(!primerId.equals(segundoId), "Los ids de dos publicaciones no deben repetirse");
    }

    @Test
    @DisplayName("data nunca viaja null: si no hay payload se publica un objeto vacío")
    void dataNuncaViajaNull() {
        publisher.publicar("empleado.retirado", Instant.parse("2026-09-21T14:30:00Z"), null);

        ArgumentCaptor<Object> captor = ArgumentCaptor.forClass(Object.class);
        verify(amqp).convertAndSend(eq("ecosistema.eventos"), eq("empleado.retirado"), captor.capture());
        Map<?, ?> envelope = (Map<?, ?>) captor.getValue();

        assertNotNull(envelope.get("data"), "El campo data del envelope nunca debe ser null");
        assertEquals(0, ((Map<?, ?>) envelope.get("data")).size());
    }

    @Test
    @DisplayName("publica JSON real (content_type application/json), no serialización JDK "
            + "(evidencia: perfiles-consumer-eventos-spring-descartados.log)")
    void publicaMensajeComoJsonConEnvelopeDelCatalogo() throws Exception {
        ConnectionFactory connectionFactory = mock(ConnectionFactory.class);
        org.springframework.amqp.rabbit.connection.Connection connection =
                mock(org.springframework.amqp.rabbit.connection.Connection.class);
        Channel channel = mock(Channel.class);
        when(connectionFactory.createConnection()).thenReturn(connection);
        when(connection.createChannel(false)).thenReturn(channel);

        RabbitEventPublisher jsonPublisher = new RabbitEventPublisher(
                new RabbitMQConfig().rabbitTemplate(connectionFactory));

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", "E001");
        data.put("estado", "ACTIVO");
        jsonPublisher.publicar("empleado.creado", Instant.parse("2026-09-21T14:30:00Z"), data);

        ArgumentCaptor<AMQP.BasicProperties> props = ArgumentCaptor.forClass(AMQP.BasicProperties.class);
        ArgumentCaptor<byte[]> body = ArgumentCaptor.forClass(byte[].class);
        verify(channel).basicPublish(eq("ecosistema.eventos"), eq("empleado.creado"),
                anyBoolean(), props.capture(), body.capture());

        assertEquals("application/json", props.getValue().getContentType(),
                "content_type debe ser application/json; la serialización JDK (x-java-serialized-object) "
                        + "hace que los consumers descarten el mensaje como malformed");

        JsonNode envelope = new ObjectMapper().readTree(body.getValue());
        assertEquals(6, envelope.size(), "El envelope del catálogo tiene exactamente 6 claves");
        assertTrue(envelope.has("id") && envelope.has("type") && envelope.has("version")
                && envelope.has("occurredAt") && envelope.has("producer") && envelope.has("data"));
        assertEquals("empleado.creado", envelope.get("type").asText());
        assertEquals("1.0", envelope.get("version").asText());
        assertEquals("2026-09-21T14:30:00Z", envelope.get("occurredAt").asText());
        assertEquals("empleados-service", envelope.get("producer").asText());
        assertEquals(4, UUID.fromString(envelope.get("id").asText()).version(), "id debe ser UUID v4");
        assertEquals("E001", envelope.get("data").get("id").asText());
        assertEquals("ACTIVO", envelope.get("data").get("estado").asText());
    }
}
