package com.empresa.gestionempleados.observability;

import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.sql.DataSource;
import java.sql.Connection;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Health check del servicio (Reto 8).
 *
 * <p>Contrato: {@code {"status":"UP|DOWN","service":"empleados-service",
 * "checks":{"database":"UP|DOWN","messageBroker":"UP|DOWN"}}}, con 200 si
 * ambos checks están UP y 503 si alguno está DOWN.
 *
 * <p>Las comprobaciones son reales: {@link DataSource#getConnection()} +
 * {@link Connection#isValid(int)} para PostgreSQL y
 * {@link ConnectionFactory#createConnection()} para RabbitMQ.
 */
@RestController
public class HealthController {

    private static final String SERVICE = "empleados-service";

    private final DataSource dataSource;
    private final ConnectionFactory rabbitConnectionFactory;

    public HealthController(DataSource dataSource,
                            ConnectionFactory rabbitConnectionFactory) {
        this.dataSource = dataSource;
        this.rabbitConnectionFactory = rabbitConnectionFactory;
    }

    @GetMapping("/health")
    public ResponseEntity<Map<String, Object>> health() {
        String database = checkDatabase();
        String broker = checkBroker();
        String status = "DOWN".equals(database) || "DOWN".equals(broker) ? "DOWN" : "UP";

        Map<String, Object> checks = new LinkedHashMap<>();
        checks.put("database", database);
        checks.put("messageBroker", broker);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", status);
        body.put("service", SERVICE);
        body.put("checks", checks);

        return ResponseEntity.status("UP".equals(status) ? 200 : 503).body(body);
    }

    private String checkDatabase() {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2) ? "UP" : "DOWN";
        } catch (Exception ex) {
            return "DOWN";
        }
    }

    private String checkBroker() {
        org.springframework.amqp.rabbit.connection.Connection connection = null;
        try {
            connection = rabbitConnectionFactory.createConnection();
            return connection.isOpen() ? "UP" : "DOWN";
        } catch (Exception ex) {
            return "DOWN";
        } finally {
            if (connection != null) {
                connection.close();
            }
        }
    }
}
