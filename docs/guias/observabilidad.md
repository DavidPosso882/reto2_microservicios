# Guía: observabilidad (logs, métricas, trazas y alertas)

Volver al [README](../../README.md) · Arquitectura: [arquitectura.md](../arquitectura.md#6-observabilidad)

## 1. Levantar el stack

```bash
docker compose up -d api-gateway                              # la aplicación
docker compose up -d prometheus grafana loki promtail zipkin  # observabilidad
```

| Herramienta | URL | Acceso |
|---|---|---|
| Grafana | http://localhost:3000 | `admin` / archivo `secrets/grafana_admin_password` |
| Prometheus | http://localhost:9091 (9090 del host es de Jenkins) | — |
| Zipkin | http://localhost:9411 | — |
| Loki | http://localhost:3100 (API; se consulta desde Grafana) | — |

El primer arranque de Grafana tarda 1–2 minutos (descarga actualizaciones de
plugins); hasta entonces el puerto 3000 no responde.

## 2. Elección de herramientas

| Necesidad | Elegido | Alternativa | Por qué |
|---|---|---|---|
| Logs centralizados | **Loki + Promtail** | ELK (Elasticsearch + Logstash + Kibana) | Indexa solo etiquetas (no el texto completo): mucho menos memoria que Elasticsearch y sin cluster; se consulta desde la misma Grafana que las métricas |
| Métricas | **Prometheus** | Datadog | Estándar abierto; cada servicio expone `/metrics` con su cliente oficial |
| Dashboards y alertas | **Grafana** | Kibana, Alertmanager | Un solo lugar para logs, métricas y trazas; alertas unificadas |
| Trazas | **Zipkin** | Jaeger | Un contenedor sin dependencias; los SDK de OpenTelemetry de los 5 lenguajes tienen exportador Zipkin; datasource nativo en Grafana. Contrapartida: almacenamiento en memoria (las trazas se pierden al recrear el contenedor) |

## 3. Logs

Cada servicio escribe **JSON a stdout** con `timestamp`, `level`, `service`,
`traceId` y `message`. Promtail descubre los contenedores por el
socket de Docker y los envía a Loki con las etiquetas `compose_service`,
`container` y `stream`. El parseo JSON se hace al consultar.

En Grafana → *Explore* → datasource **Loki**:

```logql
# Errores de un servicio
{compose_service="api-gateway"} | json | level="error"

# Todos los logs de una petición, en todos los servicios (traceId de Zipkin)
{compose_service=~".+"} | json | traceId="<traceId>"
```

## 4. Métricas y dashboard

Prometheus recoge cada 15 s el `/metrics` de los 7 servicios
(`observability/prometheus/prometheus.yml`).

El dashboard **"Reto 8 — Ecosistema de microservicios"** se aprovisiona como
código (`observability/grafana/dashboards/reto8-ecosistema.json`):

| Panel | Pregunta que responde |
|---|---|
| Estado de los servicios (up) / Servicios caídos | ¿Está vivo cada servicio? |
| Tráfico total y peticiones por servicio | ¿Cuánta carga hay y dónde? |
| Errores 4xx / 5xx por servicio y tasa de errores 5xx | ¿Quién está fallando? |
| Latencia media por servicio | ¿Quién responde lento? |

Métricas propias disponibles para consultas: `http_requests_total`,
`eventos_publicados_total` (por tipo de evento) y
`vacaciones_scheduler_transitions_total`.

## 5. Trazas distribuidas

- Los 7 servicios usan **OpenTelemetry** (agente Java en empleados; SDK en
  Node.js, Go, Python y Ruby) con exportador Zipkin.
- Propagación **W3C Trace Context** (`traceparent`): por HTTP entre gateway y
  servicios, y en las **cabeceras AMQP** de cada evento, así la traza continúa
  en los consumidores.
- Resultado: una petición de onboarding (`POST /empleados`) muestra en Zipkin
  la cascada gateway → empleados → departamentos → publicación del evento →
  auth, perfiles, notificaciones y vacaciones.
- El `traceId` de la traza es el mismo que aparece en los logs: desde un span
  de Zipkin en Grafana se saltan los logs correspondientes (datasource Zipkin
  con `tracesToLogsV2`).

Para verlo: crear un empleado (README §5), abrir http://localhost:9411 →
*Run Query* → elegir la traza de `api-gateway` `POST /empleados`.

## 6. Alertas a Telegram

Aprovisionadas desde `observability/grafana/provisioning/alerting/`:

| Regla | Condición | Espera | Severidad |
|---|---|---|---|
| **Servicio Caído** | `up` de algún servicio en 0 | 1 min | critical |
| **Alta Tasa de Errores** | más del 10 % de respuestas 5xx | 2 min | warning |

### Configurar el bot

1. En Telegram, hablar con **@BotFather** → `/newbot` → copiar el token.
2. Enviar `/start` al bot (o agregarlo al grupo destino).
3. Obtener el `chat_id`:
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | jq -r '.result[-1].message.chat.id'
   ```
4. Ponerlos en `.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) y recrear
   Grafana: `docker compose up -d grafana`.

Sin esas variables las reglas se evalúan igual, pero no se envía nada.

### Probar una alerta

```bash
docker compose stop vacaciones-service   # en 2–3 minutos llega "Servicio Caído"
docker compose start vacaciones-service  # llega el aviso de resolución
```

Más pruebas de caos (tasa de errores, recuperación):
[historial-retos.md § Pruebas de caos](../historial-retos.md#8-pruebas-de-caos).
