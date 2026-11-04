package com.empresa.gestionempleados.observability;

import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.classic.spi.ThrowableProxyUtil;
import ch.qos.logback.core.encoder.EncoderBase;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/**
 * Encoder Logback que emite una línea JSON por evento (Reto 8).
 *
 * <p>Campos base: timestamp, level, service, traceId, message. Los pares MDC
 * (por ejemplo http.method/http.path/http.status_code/duration_ms o
 * event.id/event.type) se agregan como campos de primer nivel. El traceId lo
 * inyecta el agente de OpenTelemetry en MDC ({@code trace_id}); si no está,
 * queda null.
 */
public class JsonLogEncoder extends EncoderBase<ILoggingEvent> {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String SERVICE =
            System.getenv().getOrDefault("OTEL_SERVICE_NAME", "empleados-service");
    private static final Set<String> RESERVED = Set.of(
            "timestamp", "level", "service", "traceId", "message", "logger", "thread", "exception");

    @Override
    public byte[] encode(ILoggingEvent event) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("timestamp", Instant.ofEpochMilli(event.getTimeStamp()).toString());
        payload.put("level", event.getLevel().toString());
        payload.put("service", SERVICE);
        payload.put("traceId", traceId(event));
        payload.put("message", event.getFormattedMessage());
        payload.put("logger", event.getLoggerName());
        payload.put("thread", event.getThreadName());

        for (Map.Entry<String, String> entry : event.getMDCPropertyMap().entrySet()) {
            if (RESERVED.contains(entry.getKey()) || "trace_id".equals(entry.getKey())) {
                continue;
            }
            payload.put(entry.getKey(), entry.getValue());
        }

        if (event.getThrowableProxy() != null) {
            payload.put("exception", ThrowableProxyUtil.asString(event.getThrowableProxy()));
        }

        try {
            return (MAPPER.writeValueAsString(payload) + "\n").getBytes(StandardCharsets.UTF_8);
        } catch (Exception ex) {
            // Nunca romper el logging por un fallo de serialización.
            return ("{\"level\":\"ERROR\",\"service\":\"" + SERVICE
                    + "\",\"message\":\"json log encode failed\"}\n")
                    .getBytes(StandardCharsets.UTF_8);
        }
    }

    private String traceId(ILoggingEvent event) {
        Map<String, String> mdc = event.getMDCPropertyMap();
        String traceId = mdc.get("trace_id");
        if (traceId == null || traceId.isBlank()) {
            traceId = mdc.get("traceId");
        }
        return traceId == null || traceId.isBlank() ? null : traceId;
    }

    @Override
    public byte[] headerBytes() {
        return null;
    }

    @Override
    public byte[] footerBytes() {
        return null;
    }
}
