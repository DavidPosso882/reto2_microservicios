package com.empresa.gestionempleados.client;

import com.empresa.gestionempleados.exception.DepartamentoNoDisponibleException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import java.time.Duration;

/**
 * Implementación de {@link DepartamentoClient} basada en RestClient.
 *
 * Llama a GET {DEPARTAMENTOS_URL}/departamentos/{id} con:
 *  - timeout de conexión y lectura de 2 segundos;
 *  - 3 reintentos con backoff 1s -&gt; 2s -&gt; 4s (4 intentos en total).
 *
 * Semántica:
 *  - 2xx    -&gt; el departamento existe (true).
 *  - 404    -&gt; el departamento no existe (false); es definitivo, no se reintenta.
 *  - Otros errores (5xx, timeouts de red) -&gt; reintentables; si se agotan los
 *    reintentos se rechaza la operación lanzando {@link DepartamentoNoDisponibleException}
 *    (nunca se acepta como pendiente).
 */
@Component
public class DepartamentoRestClient implements DepartamentoClient {

    private static final long[] BACKOFF_MS = {1000, 2000, 4000};
    // 4 intentos totales: 1 inicial + 3 reintentos.
    private static final int TOTAL_ATTEMPTS = 1 + BACKOFF_MS.length;

    private final RestClient restClient;

    public DepartamentoRestClient(@Value("${departamentos.url}") String departamentosUrl) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(2));
        factory.setReadTimeout(Duration.ofSeconds(2));
        this.restClient = RestClient.builder()
                .requestFactory(factory)
                .baseUrl(departamentosUrl)
                .build();
    }

    @Override
    public boolean validar(String departamentoId) {
        for (int attempt = 0; attempt < TOTAL_ATTEMPTS; attempt++) {
            try {
                var response = restClient.get()
                        .uri("/departamentos/{id}", departamentoId)
                        .retrieve()
                        .toBodilessEntity();
                return response.getStatusCode().is2xxSuccessful();
            } catch (HttpStatusCodeException ex) {
                if (ex.getStatusCode().value() == 404) {
                    // El departamento no existe: respuesta definitiva, no se reintenta.
                    return false;
                }
                // Cualquier otro código no 2xx (p. ej. 5xx) es reintentable.
                sleepBeforeRetry(attempt);
            } catch (RestClientException ex) {
                // Error de red o timeout de lectura: reintentable.
                sleepBeforeRetry(attempt);
            }
        }
        throw new DepartamentoNoDisponibleException();
    }

    private void sleepBeforeRetry(int attempt) {
        if (attempt < BACKOFF_MS.length) {
            try {
                Thread.sleep(BACKOFF_MS[attempt]);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
