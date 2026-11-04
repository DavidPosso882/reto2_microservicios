# Catálogo de Eventos del Ecosistema (normativo)

Fuente: `CATALOGO_EVENTOS.md` (secciones 1, 2, 3.1–3.3, 3.8) + las 6 secciones que
faltaban, documentadas desde la implementación verificada
(`microservicios/autenticacion/src/service/UsuarioService.js`,
`microservicios/gestion-vacaciones/app/publisher.rb`). En caso de discrepancia
con el catálogo oficial de la materia, prevalece el oficial.

Resumen:

| Evento | Publicado por | Consumido por |
|--------|---------------|---------------|
| `empleado.creado` | Gestión de Empleados | Autenticación, Perfiles, Notificaciones |
| `empleado.actualizado` | Gestión de Empleados | Perfiles |
| `empleado.retirado` | Gestión de Empleados | Autenticación, Perfiles, Notificaciones |
| `usuario.creado` | Autenticación | Notificaciones |
| `usuario.recuperacion` | Autenticación | Notificaciones |
| `cuenta.activada` | Autenticación | Notificaciones |
| `cuenta.desactivada` | Autenticación | Notificaciones |
| `vacaciones.programadas` | Gestión de Vacaciones | Notificaciones |
| `vacaciones.iniciadas` | Gestión de Vacaciones | Autenticación, Notificaciones |
| `vacaciones.finalizadas` | Gestión de Vacaciones | Autenticación, Notificaciones |

## 1. Envelope común (todos los eventos)

```json
{
  "id": "<uuid v4>",
  "type": "empleado.creado",
  "version": "1.0",
  "occurredAt": "<ISO-8601 UTC>",
  "producer": "empleados-service",
  "data": {}
}
```

`id` es la clave de deduplicación: todo consumer mantiene
`eventos_procesados(id PK, ...)` y descarta el mensaje si el `id` ya existe.
Transporte RabbitMQ: exchange `ecosistema.eventos` (topic, durable),
routing key = `type`. Colas durables por consumer con ACK manual después de
persistir efecto + `id`. Las cabeceras AMQP propagan W3C
(traceparent/tracestate/baggage): una sola traza de onboarding de punta a punta
(verificado: 51 spans, 7 servicios, Zipkin).

## 2. `empleado.creado` → `empleados-service`

Tras `POST /empleados` (estados `ACTIVO` o `PENDIENTE_VALIDACION` con fallback).
`data` = foto completa del empleado (`id`, `nombre`, `apellido`, `email`,
`numeroEmpleado`, `cargo`, `area`, `departamentoId`, `fechaIngreso`, `estado`).

## 3. `empleado.actualizado` → `empleados-service`

Tras `PUT /empleados/{id}`. Misma foto completa actualizada. Perfiles sincroniza
solo identidad (`nombre`, `apellido`, `email`); nunca pisa `telefono`,
`direccion`, `ciudad`, `biografia`.

## 4. `empleado.retirado` → `empleados-service`

Tras `DELETE /empleados/{id}` (baja lógica a `RETIRADO` + `fechaRetiro`).
`data`: `id`, `nombre`, `apellido`, `email`, `estado: RETIRADO`,
`fechaRetiro` (= `occurredAt`).

## 5. `usuario.creado` → `autenticacion-service`

Al aplicar `empleado.creado`: cuenta en estado inactivo, `passwordHash: null`
(sin contraseña válida) + token de activación con expiración.

```json
{ "empleadoId": "E001", "email": "e001@empresa.com",
  "nombre": "Ada", "apellido": "Lovelace", "resetToken": "<JWT RESET_PASSWORD 30min>" }
```

Notificaciones envía la bienvenida **con el token, nunca una contraseña**.

## 6. `usuario.recuperacion` → `autenticacion-service`

Al solicitar recuperación (`POST /auth/recover-password` con email existente).

```json
{ "email": "e001@empresa.com", "empleadoId": "E001",
  "resetToken": "<JWT RESET_PASSWORD 30min>", "expiracion": "30min" }
```

## 7. `cuenta.activada` → `autenticacion-service`

Al establecer la contraseña con un token válido
(`ESTABLECIMIENTO_PASSWORD`): la cuenta pasa a `ACTIVA`.

```json
{ "email": "e001@empresa.com", "empleadoId": "E001", "motivo": "ESTABLECIMIENTO_PASSWORD" }
```

Nunca se publica para cuentas con baja permanente: un reset sobre
`DESACTIVADA_PERMANENTE` responde error uniforme sin reactivar.

## 8. `cuenta.desactivada` → `autenticacion-service`

Suspensión temporal (vacaciones, `motivo: VACACIONES`, reversible) o baja
permanente (retiro, `motivo: RETIRO`, `permanente: true`, irreversible).

```json
{ "email": "e001@empresa.com", "empleadoId": "E001", "motivo": "VACACIONES|RETIRO" }
```

## 9. `vacaciones.programadas` → `vacaciones-service`

Tras `POST /vacaciones` (`PROGRAMADA`). No desactiva cuentas.

```json
{ "id": "V-2026-0042", "empleadoId": "E001", "empleadoEmail": "e001@empresa.com",
  "fechaInicio": "2026-12-15", "fechaFin": "2026-12-30",
  "estado": "PROGRAMADA", "fechaCreacion": "<ISO-8601 UTC>" }
```

`empleadoEmail` desnormalizado: Notificaciones no consulta a nadie.

## 10. `vacaciones.iniciadas` → `vacaciones-service`

El scheduler (cada `SCHEDULER_INTERVAL_S`, default 60s) mueve `PROGRAMADA` →
`EN_CURSO` y publica. Autenticación suspende la cuenta (temporal);
Notificaciones avisa. Mismo `data` que §9 con `estado: EN_CURSO`.

## 11. `vacaciones.finalizadas` → `vacaciones-service`

El scheduler mueve `EN_CURSO` → `FINALIZADA` y publica. Autenticación reactiva
la cuenta (salvo baja permanente concurrente: el retiro gana).
Mismo `data` que §9 con `estado: FINALIZADA`.
