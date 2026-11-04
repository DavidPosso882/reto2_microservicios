package com.empresa.gestionempleados.observability;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

/**
 * Log de acceso JSON por petición HTTP (Reto 8): método, ruta, estado,
 * duración y traceId (MDC del agente OTel o cabecera W3C traceparent).
 *
 * <p>Nunca registra cabeceras de autorización ni cuerpos: solo metadatos.
 */
@Component
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger("http.request");
    private static final String[] MDC_KEYS = {
            "http.method", "http.path", "http.status_code", "duration_ms", "trace_id"
    };

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {
        long started = System.nanoTime();
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.put("http.method", request.getMethod());
            MDC.put("http.path", request.getRequestURI());
            MDC.put("http.status_code", String.valueOf(response.getStatus()));
            MDC.put("duration_ms",
                    String.valueOf(TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started)));
            if (MDC.get("trace_id") == null) {
                String traceId = traceIdFromTraceparent(request.getHeader("traceparent"));
                if (traceId != null) {
                    MDC.put("trace_id", traceId);
                }
            }
            log.info("http_request");
            for (String key : MDC_KEYS) {
                MDC.remove(key);
            }
        }
    }

    /** traceparent = version-traceId-spanId-flags (W3C). */
    private String traceIdFromTraceparent(String traceparent) {
        if (traceparent == null) {
            return null;
        }
        String[] parts = traceparent.split("-");
        return parts.length >= 4 ? parts[1] : null;
    }
}
