# Evidencias Reto 8 — Observabilidad (pendientes de stack vivo)

Esta carpeta **no contiene capturas todavía**. La tarea T3 (dashboard,
alertas y documentación) se cerró sin levantar el stack (`docker compose up`
queda fuera de su alcance), así que las capturas se tomarán en la validación
final del reto. No se inventa ninguna imagen.

Cuando se capturen, guardarlas aquí con estos nombres exactos y actualizar la
tabla del README raíz (§Reto 8 → "Capturas").

## 1. Dashboard consolidado (S4)

| Campo | Valor |
|---|---|
| Archivo sugerido | `reto8-dashboard.png` |
| Qué debe mostrar | Fila **Resumen** con los 7 servicios en `UP` (verde) y fila **Tráfico** con las series de peticiones, latencia y errores de más de un servicio |
| Cómo llegar | http://localhost:3000 → carpeta **Reto 8** → *Reto 8 — Ecosistema de microservicios* |
| Genera tráfico antes | `for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:8080/health; done` |

## 2. Traza distribuida en Zipkin (S2)

| Campo | Valor |
|---|---|
| Archivo sugerido | `reto8-zipkin-traza.png` |
| Qué debe mostrar | Cascada de spans con **un solo traceId**: `api-gateway` → `empleados-service` → `departamentos-service` (y la rama asíncrona `perfiles-service` / `notificaciones-service` si se captura el flujo de eventos) |
| Cómo llegar | http://localhost:9411 → *Run Query* → abrir la traza más reciente de `api-gateway` |
| Traza obligatoria del scheduler | `reto8-zipkin-scheduler.png` — span raíz manual de `vacaciones-service` → `auth-service` → `notificaciones-service` (misma cascada, no tres trazas sueltas) |

## 3. Alerta recibida en Telegram (S5)

| Campo | Valor |
|---|---|
| Archivo sugerido | `reto8-alerta-telegram.png` |
| Qué debe mostrar | Mensaje del bot en el chat con el título **Servicio Caído**, el `job` afectado y la hora (y, si se espera, el mensaje de resolución) |
| Prerrequisito | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` reales en el entorno del contenedor Grafana (ver README §Reto 8 → "Canal de alertas (Telegram)") |
| Cómo provocarla | `docker compose stop departamentos-service`, esperar ~2–3 min y capturar el chat |

## 4. Estado del target caído en Prometheus

| Campo | Valor |
|---|---|
| Archivo sugerido | `reto8-prometheus-target-down.png` |
| Qué debe mostrar | Target `departamentos-service` en estado **DOWN** en http://localhost:9091/targets (y/o la regla en estado `Firing` en Grafana → Alerting) |

## 5. Respuesta a la pregunta de cierre del reto

> "¿Qué servicio del ecosistema tardó más en responder y cómo lo identificaron?"

Pendiente de medir con el stack vivo: se responde con el panel **Latencia
media por servicio** (ordenado por `max`), confirmando la ruta lenta en la
traza de Zipkin. Guardar la respuesta junto a `reto8-dashboard.png`.

## Checklist

- [ ] `reto8-dashboard.png` — dashboard con métricas reales de varios servicios
- [ ] `reto8-zipkin-traza.png` — cascada HTTP completa con un solo traceId
- [ ] `reto8-zipkin-scheduler.png` — cascada del scheduler de vacaciones
- [ ] `reto8-alerta-telegram.png` — alerta "Servicio Caído" en el chat
- [ ] `reto8-prometheus-target-down.png` — target DOWN / regla Firing
- [ ] Respuesta escrita a la pregunta de latencia
