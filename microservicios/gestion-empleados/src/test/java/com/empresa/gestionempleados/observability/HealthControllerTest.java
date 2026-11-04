package com.empresa.gestionempleados.observability;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpException;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.http.ResponseEntity;

import javax.sql.DataSource;
import java.sql.SQLException;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * Unitarias del health check Reto 8 (sin Spring ni Docker): DataSource y
 * ConnectionFactory se mockean para cubrir UP/DOWN de DB y broker.
 */
class HealthControllerTest {

    private DataSource dataSource;
    private java.sql.Connection sqlConnection;
    private ConnectionFactory rabbitFactory;
    private org.springframework.amqp.rabbit.connection.Connection rabbitConnection;
    private HealthController controller;

    @BeforeEach
    void setUp() throws Exception {
        dataSource = mock(DataSource.class);
        sqlConnection = mock(java.sql.Connection.class);
        rabbitFactory = mock(ConnectionFactory.class);
        rabbitConnection = mock(org.springframework.amqp.rabbit.connection.Connection.class);

        when(dataSource.getConnection()).thenReturn(sqlConnection);
        when(sqlConnection.isValid(anyInt())).thenReturn(true);
        when(rabbitFactory.createConnection()).thenReturn(rabbitConnection);
        when(rabbitConnection.isOpen()).thenReturn(true);

        controller = new HealthController(dataSource, rabbitFactory);
    }

    @Test
    @DisplayName("DB y broker UP -> 200 con status UP y checks UP")
    void healthUp() {
        ResponseEntity<Map<String, Object>> response = controller.health();

        assertEquals(200, response.getStatusCode().value());
        assertEquals("UP", response.getBody().get("status"));
        assertEquals("empleados-service", response.getBody().get("service"));
        Map<?, ?> checks = (Map<?, ?>) response.getBody().get("checks");
        assertEquals("UP", checks.get("database"));
        assertEquals("UP", checks.get("messageBroker"));
        verify(rabbitConnection).close();
    }

    @Test
    @DisplayName("DB DOWN -> 503 y checks.database DOWN")
    void databaseDown() throws Exception {
        when(sqlConnection.isValid(anyInt())).thenReturn(false);

        ResponseEntity<Map<String, Object>> response = controller.health();

        assertEquals(503, response.getStatusCode().value());
        assertEquals("DOWN", response.getBody().get("status"));
        assertEquals("DOWN", ((Map<?, ?>) response.getBody().get("checks")).get("database"));
    }

    @Test
    @DisplayName("broker DOWN -> 503 y checks.messageBroker DOWN")
    void brokerDown() {
        when(rabbitConnection.isOpen()).thenReturn(false);

        ResponseEntity<Map<String, Object>> response = controller.health();

        assertEquals(503, response.getStatusCode().value());
        assertEquals("DOWN", response.getBody().get("status"));
        assertEquals("DOWN", ((Map<?, ?>) response.getBody().get("checks")).get("messageBroker"));
    }

    @Test
    @DisplayName("excepciones de conexión -> 503 con ambos checks DOWN")
    void connectionErrors() throws Exception {
        when(dataSource.getConnection()).thenThrow(new SQLException("db down"));
        when(rabbitFactory.createConnection()).thenThrow(new AmqpException("broker down"));

        ResponseEntity<Map<String, Object>> response = controller.health();

        assertEquals(503, response.getStatusCode().value());
        assertEquals("DOWN", response.getBody().get("status"));
        Map<?, ?> checks = (Map<?, ?>) response.getBody().get("checks");
        assertEquals("DOWN", checks.get("database"));
        assertEquals("DOWN", checks.get("messageBroker"));
    }
}
