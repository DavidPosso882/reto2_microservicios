# Eventos implementados

Volver al [README](../README.md) · Arquitectura: [arquitectura.md](arquitectura.md)

El contrato normativo (envelope, cargas útiles y reglas) está en
[CATALOGO_EVENTOS.md](../CATALOGO_EVENTOS.md). Este documento resume lo que
**está implementado** en el código: quién publica, quién consume, en qué cola
y con qué efecto.

## 1. Transporte

| Elemento | Valor |
|---|---|
| Broker | RabbitMQ 3 |
| Exchange | `ecosistema.eventos`, tipo **topic**, durable |
| Routing key | igual al campo `type` del evento (p. ej. `empleado.creado`) |
| Colas | una durable por servicio consumidor; cada una se enlaza solo a las claves que le interesan |
| Entrega | mensajes persistentes; **ACK manual** solo después de guardar el efecto y la marca de deduplicación |
| Fallos | error transitorio → `nack` con reencolado (auth y notificaciones aplican además backoff creciente); mensaje inválido (sin `id`, JSON roto) → se descarta con ACK y se registra en el log |
| Trazas | el productor inyecta `traceparent`/`tracestate` en las cabeceras AMQP y el consumidor continúa la misma traza |

## 2. Envelope común

```json
{
  "id": "6f1c2e0a-8d1b-4a51-9a5e-2f9b7c1d3e44",
  "type": "empleado.creado",
  "version": "1.0",
  "occurredAt": "2026-11-10T18:40:00Z",
  "producer": "empleados-service",
  "data": { "...": "carga útil del evento" }
}
```

## 3. Eventos

| Evento | Productor | Consumidores (cola) | Efecto |
|---|---|---|---|
| `empleado.creado` | empleados | auth (`q.auth`), perfiles (`q.perfiles`), notificaciones (`q.notificaciones`), vacaciones (`q.vacaciones.empleados`) | cuenta inactiva + token de activación · perfil por defecto · notificación BIENVENIDA · alta en la réplica local |
| `empleado.actualizado` | empleados | perfiles | sincroniza nombre, apellido y email (no pisa los datos que editó el empleado) |
| `empleado.retirado` | empleados | auth, perfiles, notificaciones, vacaciones | baja **permanente** de la cuenta · perfil `archivado=true` · notificación DESVINCULACION · baja en la réplica local |
| `usuario.creado` | auth | notificaciones | bienvenida con el **token de activación** (nunca una contraseña) |
| `usuario.recuperacion` | auth | notificaciones | aviso con el token de recuperación |
| `cuenta.activada` | auth | notificaciones | aviso de cuenta activa (activación o regreso de vacaciones) |
| `cuenta.desactivada` | auth | notificaciones | aviso de suspensión (vacaciones) o baja (retiro) |
| `vacaciones.programadas` | vacaciones | notificaciones | confirmación del período |
| `vacaciones.iniciadas` | vacaciones (scheduler) | auth, notificaciones | **suspensión temporal** de la cuenta → `cuenta.desactivada` |
| `vacaciones.finalizadas` | vacaciones (scheduler) | auth, notificaciones | **reactivación** de la cuenta → `cuenta.activada` (nunca si fue retirada) |

### Claves enlazadas por cola

| Cola | Servicio | Routing keys |
|---|---|---|
| `q.auth` | auth-service | `empleado.creado`, `empleado.retirado`, `vacaciones.iniciadas`, `vacaciones.finalizadas` |
| `q.perfiles` | perfiles-service | `empleado.creado`, `empleado.actualizado`, `empleado.retirado` |
| `q.notificaciones` | notificaciones-service | `empleado.creado`, `empleado.retirado`, `vacaciones.programadas`, `usuario.creado`, `usuario.recuperacion`, `cuenta.activada`, `cuenta.desactivada`, `vacaciones.iniciadas`, `vacaciones.finalizadas` |
| `q.vacaciones.empleados` | vacaciones-service | `empleado.creado`, `empleado.retirado` |

## 4. Deduplicación (consumidores idempotentes)

Cada consumidor guarda el `id` del envelope en una tabla
`eventos_procesados (id PRIMARY KEY)` **en la misma transacción** que el
efecto. Si el mensaje llega de nuevo (reentrega tras un fallo, publicación
duplicada), el `id` ya existe y se confirma con ACK sin repetir el efecto.

| Servicio | Mecanismo |
|---|---|
| auth-service | `eventos_procesados` + ACK tras marcar |
| perfiles-service | efecto + marca en una transacción |
| notificaciones-service | efecto + marca en una transacción (PK como respaldo) |
| vacaciones-service | efecto en la réplica local + marca en una transacción |

Evidencia reproducible (publicar dos veces el mismo envelope por la API de
RabbitMQ y comprobar un solo efecto):
[historial-retos.md § Evidencia de deduplicación](historial-retos.md#13-evidencia-de-deduplicación).

## 5. Scheduler de vacaciones

Cada `SCHEDULER_INTERVAL_S` segundos (60 por defecto):

- `PROGRAMADA` con `fechaInicio <= hoy` → `EN_CURSO` y publica `vacaciones.iniciadas`.
- `EN_CURSO` con `fechaFin <= hoy` → `FINALIZADA` y publica `vacaciones.finalizadas`.

Las transiciones son idempotentes (`UPDATE ... WHERE estado = <anterior>
RETURNING id`): solo se publican eventos por filas que realmente cambiaron.
