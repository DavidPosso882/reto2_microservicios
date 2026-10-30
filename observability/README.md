# Observabilidad del ecosistema (Reto 8)

Configuración como código del stack de observabilidad. Todo se levanta desde el
`docker-compose.yml` raíz (S3): no hay pasos manuales en la UI.

| Servicio   | Imagen                  | URL desde el host         | Para qué |
|------------|-------------------------|---------------------------|----------|
| Prometheus | `prom/prometheus`       | http://localhost:9091     | métricas de los 7 servicios |
| Grafana    | `grafana/grafana`       | http://localhost:3000     | dashboards (admin/admin por defecto) |
| Loki       | `grafana/loki`          | http://localhost:3100     | almacén de logs |
| Promtail   | `grafana/promtail`      | — (sin puerto)            | recolecta logs vía socket Docker |
| Zipkin     | `openzipkin/zipkin`     | http://localhost:9411     | trazas distribuidas |

## Decisión: Prometheus publica en 9091, no en 9090

El reto pide Prometheus en 9090, pero **Jenkins ya publica el 9090 del host**
(`9090:8080`, Reto 7). Para no romper Jenkins:

- Prometheus sigue escuchando en **9090 dentro del contenedor** (estándar de la
  imagen y URL que consumen Grafana y Prometheus: `http://prometheus:9090`).
- Se publica en el host como **9091** → http://localhost:9091.
- Jenkins no se toca: sigue en http://localhost:9090.

## Contrato con T2 (instrumentación)

- Cada servicio expone `GET /metrics` en formato Prometheus, en el mismo puerto
  interno que ya usa en la red Docker (8080 gateway, 8081 empleados, 8082
  departamentos, 8083 perfiles, 8084 notificaciones, 8085 vacaciones, 8086 auth).
- Los targets de Prometheus se resuelven por **nombre de servicio** de la red
  `microservices-network`, así que ningún puerto nuevo hace falta publicar.
- Si un servicio expone las métricas en otra ruta (p. ej.
  `/actuator/prometheus`), basta con ajustar su `metrics_path` en
  `prometheus/prometheus.yml`.
- Los logs JSON aparecen en Loki con las etiquetas `container`,
  `compose_service`, `compose_project` y `stream`.

## Estructura

```
observability/
├── prometheus/prometheus.yml                        # 7 scrape_jobs, api-gateway primero, 15s
├── loki/loki-config.yml                             # single binary + filesystem + TSDB v13
├── promtail/promtail-config.yml                     # docker_sd contra /var/run/docker.sock
└── grafana/
    ├── provisioning/datasources/datasources.yml     # Prometheus + Loki + Zipkin (uid estables)
    ├── provisioning/dashboards/dashboards.yml       # proveedor de dashboards JSON
    └── dashboards/                                  # placeholder para T3
```

## Verificación

```bash
docker compose config --quiet          # valida el compose completo
docker compose up -d prometheus grafana loki promtail zipkin
# Prometheus ve los 7 targets:
curl -s http://localhost:9091/api/v1/targets | jq '.data.activeTargets[].labels.job'
```

`promtool check config observability/prometheus/prometheus.yml` valida además el
contenido semántico de la configuración de Prometheus (no viene instalado en el
host; se puede ejecutar desde la imagen `prom/prometheus`).
