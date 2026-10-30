# Dashboards de Grafana (Reto 8, S4)

El proveedor `reto8-ecosistema` (ver
`../provisioning/dashboards/dashboards.yml`) escanea esta carpeta cada 30s y
carga en la carpeta **Reto 8** cada `*.json` que encuentre aquí. La fuente de
verdad es el JSON del repositorio: `allowUiUpdates: false` + volumen `:ro`, así
que las ediciones hechas en la UI no se persisten.

| Fichero | uid | Contenido |
|---|---|---|
| `reto8-ecosistema.json` | `reto8-ecosistema` | Dashboard consolidado multi-servicio: 2 filas (`Resumen`, `Tráfico`) y 7 paneles |

## Paneles

| Fila | Panel | Tipo | Consulta (resumen) |
|---|---|---|---|
| Resumen | Estado de los servicios (up) | Stat | `up{job=~"$job"}` → 1 `UP` / 0 `DOWN` por servicio |
| Resumen | Servicios caídos | Stat | `sum(up{job=~"$job"} == 0) or vector(0)` |
| Resumen | Tráfico total (req/s) | Stat | `sum(rate(http_requests_total[1m])) + sum(rate(http_server_requests_seconds_count[1m]))` |
| Resumen | Tasa de errores 5xx | Stat | 5xx / total (mismo cálculo que la alerta) |
| Tráfico | Peticiones por servicio | Timeseries | `sum by (service) (rate(http_requests_total[1m]))` + rama micrometer |
| Tráfico | Latencia media por servicio | Timeseries | `rate(_sum[1m]) / rate(_count[1m])` por cada familia de métricas |
| Tráfico | Errores 4xx / 5xx por servicio | Timeseries | `code=~"4..|5.."` (Node/Go/Ruby), `status=~"4..|5.."` (Python y Java) |

Los paneles del dashboard referencian el datasource por **uid**
(`{"type":"prometheus","uid":"prometheus"}`), nunca por nombre. Loki y Zipkin
también están aprovisionados con uid estable (`loki`, `zipkin`) para explorar
logs y trazas, pero el dashboard es sólo de métricas: los enlaces de cabecera
llevan a Prometheus y a la UI de Zipkin.

## Por qué hay consultas duplicadas por familia de métricas

Los 7 servicios no publican el mismo nombre de métrica ni las mismas etiquetas:

| Familia | Métrica de peticiones | Etiqueta de código HTTP |
|---|---|---|
| Node.js (`prom-client`) | `http_requests_total` | `code` |
| Go (`client_golang`) | `http_requests_total` | `code` |
| Ruby (`prometheus-client`) | `http_requests_total` | `code` |
| Python (`prometheus-fastapi-instrumentator`) | `http_requests_total` | `status` |
| Java (`micrometer-registry-prometheus`) | `http_server_requests_seconds_count` | `status` |

PromQL no permite unir dos nombres de métrica en un selector, así que cada
panel declara una consulta por familia y todas comparten `legendFormat`
`{{service}}`. La etiqueta `service` llega del `labels:` de cada `scrape_job`
en `observability/prometheus/prometheus.yml` (y coincide con el default label
de prom-client / client_golang, que Prometheus renombra a `exported_service`
sin romper el scrape).

`prometheus-fastapi-instrumentator` (≥ 0.6, el pin del repo es 7.1.0) nombra la
etiqueta del código HTTP `status`; en versiones antiguas era `status_code` y
habría que añadir esa variante a las consultas de errores.

El panel "Latencia media" marca en rojo discontinuo el umbral de 2 s (la regla
opcional "Alta Latencia" del reto, no aprovisionada).
