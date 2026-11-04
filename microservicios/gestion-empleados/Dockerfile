# ── Etapa 1: build ──────────────────────────────────────────────────────────
FROM maven:3.9.6-eclipse-temurin-21 AS build

WORKDIR /app

# Copiar solo el pom primero para aprovechar la caché de capas de Docker
COPY pom.xml .
RUN mvn dependency:go-offline -B

# Copiar el código fuente y compilar
COPY src ./src
RUN mvn package -DskipTests -B

# ── Etapa 2: runtime ─────────────────────────────────────────────────────────
FROM eclipse-temurin:21-jre

WORKDIR /app

# Instalar curl (útil para health checks y pruebas dentro del contenedor)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Reto 8: agente de OpenTelemetry Java (instrumentación automática de HTTP,
# JDBC y Spring AMQP) con exportador Zipkin y propagación W3C.
RUN curl -fsSL -o /app/opentelemetry-javaagent.jar \
    https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.10.0/opentelemetry-javaagent.jar

ENV OTEL_SERVICE_NAME=empleados-service \
    OTEL_TRACES_EXPORTER=zipkin \
    OTEL_EXPORTER_ZIPKIN_ENDPOINT=http://zipkin:9411/api/v2/spans \
    OTEL_PROPAGATORS=tracecontext,baggage \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none

# Copiar el JAR generado en la etapa de build
COPY --from=build /app/target/gestion-empleados-1.0.0.jar app.jar

# Exponer el puerto en el que corre el servidor
EXPOSE 8081

# Comando de arranque (Reto 8: agente OTel + jar de la aplicación)
ENTRYPOINT ["java", "-javaagent:/app/opentelemetry-javaagent.jar", "-jar", "app.jar"]
