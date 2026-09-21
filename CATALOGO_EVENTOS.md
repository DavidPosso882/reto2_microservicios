# Catálogo de Eventos del Ecosistema — PROPUESTA (pendiente de validación)

> Estado: **normativo validado por el usuario (2026-09-21)**. Rige para todo el ecosistema.
> Si aparece el catálogo oficial de la materia, este archivo se ajusta a él y el oficial
> prevalece en caso de discrepancia.
>
> Decisiones validadas: `empleado.actualizado` lleva foto completa; `empleado.creado` se publica
> también en fallback `PENDIENTE_VALIDACION` con el estado real; el id de vacaciones lo genera el
> servidor (`V-AAAA-NNNN`) y programar para un `RETIRADO` se rechaza con 400.

## 1. Envelope común (todos los eventos)

```json
{
  "id": "b3b3c3f2-1a2b-4c5d-8e9f-0a1b2c3d4e5f",
  "type": "empleado.creado",
  "version": "1.0",
  "occurredAt": "2026-09-21T14:30:00Z",
  "producer": "empleados-service",
  "data": { "...": "payload específico de la sección" }
}
```

| Campo | Tipo | Reglas |
|---|---|---|
| `id` | string (UUID v4) | Generado por el productor en cada publicación. **Es la clave de deduplicación**: todo consumer mantiene `eventos_procesados(id PK, procesado_en)` y descarta el mensaje si el `id` ya existe. |
| `type` | string | Uno de los 4 nombres exactos de este catálogo. Case-sensitive, con punto. |
| `version` | string | `"1.0"` para todos en este reto. Cambios incompatibles futuros → `"2.0"`. |
| `occurredAt` | string | ISO-8601 en UTC (`...Z`). Momento del hecho de dominio, no de la publicación. |
| `producer` | string | Nombre del servicio Docker que publica (`empleados-service`, `vacaciones-service`). |
| `data` | object | Payload de la sección correspondiente. Nunca `null`. |

## 2. Transporte (RabbitMQ — decisión del usuario)

- Exchange: `ecosistema.eventos`, tipo **topic**, durable.
- Routing key = `type` del evento (ej. `empleado.creado`).
- Cada servicio consumer declara **su propia cola durable** y la enlaza solo a las keys que le
  corresponden → el fan-out sale gratis (cada cola recibe su copia):
  - `q.notificaciones` ← `empleado.creado`, `empleado.retirado`, `vacaciones.programadas`
  - `q.perfiles` ← `empleado.creado`, `empleado.actualizado`, `empleado.retirado`
  - `q.vacaciones.empleados` ← `empleado.creado`, `empleado.retirado` (réplica local, opción b)
- ACK manual **después** de persistir el efecto + el `id` en `eventos_procesados` (en la misma
  transacción cuando la BD lo permita). Si el proceso cae antes del ACK, el broker reentrega y la
  deduplicación por `id` evita el doble efecto.

## 3. Eventos (normativa propuesta)

### 3.1 `empleado.creado` — producer: `empleados-service`

Se publica tras `POST /empleados` exitoso (estado `ACTIVO` o `PENDIENTE_VALIDACION`).

Consumers: `notificaciones-service` (bienvenida), `perfiles-service` (perfil por defecto),
`vacaciones-service` (alta en réplica local).

```json
{
  "id": "<uuid>",
  "type": "empleado.creado",
  "version": "1.0",
  "occurredAt": "<ISO-8601 UTC>",
  "producer": "empleados-service",
  "data": {
    "id": "E001",
    "nombre": "Juan",
    "apellido": "Pérez",
    "email": "juan.perez@empresa.com",
    "numeroEmpleado": "EMP-2026-001",
    "cargo": "Desarrollador Senior",
    "area": "Tecnología",
    "departamentoId": "IT",
    "fechaIngreso": "2026-03-01",
    "estado": "ACTIVO"
  }
}
```

El `data` es la **foto completa** del empleado (mismo modelo canónico del REST). Decisión propuesta:
foto completa y no delta, para que los consumers sean idempotentes y no dependan del orden.

### 3.2 `empleado.actualizado` — producer: `empleados-service`

Se publica tras `PUT /empleados/{id}` exitoso. Mismo `data` que 3.1 con los valores ya actualizados.

Consumer: `perfiles-service` (sincroniza `nombre`, `apellido`, `email` replicados; nunca pisa
`telefono`, `direccion`, `ciudad`, `biografia`, que son propios del perfil).

### 3.3 `empleado.retirado` — producer: `empleados-service`

Se publica tras `DELETE /empleados/{id}` (baja lógica: `estado → RETIRADO` + `fechaRetiro`).

Consumers: `notificaciones-service` (desvinculación), `perfiles-service` (archiva, no borra),
`vacaciones-service` (baja en réplica local; los períodos `PROGRAMADA` del empleado quedan
huérfanos de validación futura pero se conservan para auditoría).

```json
{
  "id": "<uuid>",
  "type": "empleado.retirado",
  "version": "1.0",
  "occurredAt": "<ISO-8601 UTC = fechaRetiro>",
  "producer": "empleados-service",
  "data": {
    "id": "E001",
    "nombre": "Juan",
    "apellido": "Pérez",
    "email": "juan.perez@empresa.com",
    "estado": "RETIRADO",
    "fechaRetiro": "2026-09-21T14:30:00Z"
  }
}
```

### 3.8 `vacaciones.programadas` — producer: `vacaciones-service`

Se publica tras `POST /vacaciones` exitoso (estado `PROGRAMADA`).

Consumer: `notificaciones-service` (confirmación tipo `VACACIONES`).
**No** desactiva cuentas; eso es `vacaciones.iniciadas` del Reto 5.

```json
{
  "id": "<uuid>",
  "type": "vacaciones.programadas",
  "version": "1.0",
  "occurredAt": "<ISO-8601 UTC = fechaCreacion>",
  "producer": "vacaciones-service",
  "data": {
    "id": "V-2026-0042",
    "empleadoId": "E001",
    "empleadoEmail": "juan.perez@empresa.com",
    "fechaInicio": "2026-12-15",
    "fechaFin": "2026-12-30",
    "estado": "PROGRAMADA",
    "fechaCreacion": "2026-09-21T14:30:00Z"
  }
}
```

`empleadoEmail` se incluye desnormalizado para que Notificaciones no necesite consultar a nadie
(servicio puramente reactivo, sin llamadas REST salientes).

## 4. Preguntas abiertas para el usuario (validar junto con el contrato)

1. ¿Foto completa en `empleado.actualizado` o solo delta de cambiados?
2. ¿`empleado.creado` se publica también cuando el estado es `PENDIENTE_VALIDACION` (fallback del
   Circuit Breaker), o solo con `ACTIVO`? Propuesta: se publica igual, con el `estado` real.
3. ¿El `id` de vacaciones lo genera el cliente o el servidor (`V-AAAA-NNNN`)? Propuesta: servidor.
4. ¿Vacaciones de un empleado `RETIRADO` se rechazan con 400? Propuesta: sí, el empleado debe estar
   `ACTIVO` (o `EN_VACACIONES` para períodos futuros) según la réplica local.
