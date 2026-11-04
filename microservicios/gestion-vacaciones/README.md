# vacaciones-service

Servicio **productor** del ecosistema (Reto 4 — comunicación asincrónica):

- **Expone REST** para gestionar períodos de vacaciones. El `id` lo genera el
  servidor con formato `V-AAAA-NNNN` (año actual + secuencial de 4 dígitos,
  resuelto con MAX+1 dentro de la transacción de inserción).
- **Publica** los eventos `vacaciones.programadas` (catálogo 3.8) tras cada
  programación exitosa y, desde el Reto 5, `vacaciones.iniciadas` y
  `vacaciones.finalizadas` cuando el scheduler transiciona el ciclo de vida.
  Un fallo de publish se registra en el log y **no** revierte la base de datos.
- **Consume** `empleado.creado` y `empleado.retirado` (catálogos 3.1 y 3.3)
  para mantener una **réplica local de empleados** (opción b: validación por
  eventos, sin llamadas REST salientes).
- **Scheduler del ciclo de vida (Reto 5)**: hilo de fondo que cada
  `SCHEDULER_INTERVAL_S` segundos aplica `PROGRAMADA → EN_CURSO → FINALIZADA`
  por fecha y publica los eventos correspondientes.

Contrato normativo: `CATALOGO_EVENTOS.md` en la raíz del repositorio.

## Stack

- Ruby 3.3, Sinatra, `bunny` (AMQP), `pg` (Postgres), Puma.
- Postgres 16 (BD propia: `vacaciones`, contenedor `database-vacaciones`).

## Configuración (variables de entorno, con defaults locales)

| Variable | Default |
|---|---|
| `PORT` | `8085` |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` |
| `DB_NAME` | `vacaciones` |
| `DB_USER` / `DB_PASSWORD` | `postgres` / `postgres` |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | `localhost` / `5672` |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | `guest` / `guest` |
| `SCHEDULER_INTERVAL_S` | `60` (mínimo 1; frecuencia del scheduler del ciclo de vida) |

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Health check: `{"status":"ok","service":"vacaciones-service"}` |
| GET | `/openapi.yaml` | Especificación OpenAPI servida por el propio servicio |
| GET | `/vacaciones` | Lista todos los períodos (200, arreglo) |
| GET | `/vacaciones?empleadoId=E001` | Lista filtrada por empleado |
| GET | `/vacaciones/{id}` | Período por id (200 / 404 `{"status":404,"error":"..."}`) |
| POST | `/vacaciones` | Programar: `{empleadoId, fechaInicio, fechaFin}` → 201 |
| DELETE | `/vacaciones/{id}` | Si aún no inició → `CANCELADA` (200); si ya inició → 400; inexistente → 404 |

Estados (Reto 5): `PROGRAMADA`, `EN_CURSO`, `FINALIZADA` y `CANCELADA`.

## Scheduler: ciclo de vida de las vacaciones (Reto 5)

`app/scheduler.rb` corre en un hilo de fondo (junto al consumer, ver
`Boot.build/run!`) y cada `SCHEDULER_INTERVAL_S` segundos (default 60) aplica
por FECHA (columnas `DATE`, sin hora):

- `PROGRAMADA` con `fechaInicio <= hoy` → `EN_CURSO` y publica
  `vacaciones.iniciadas`.
- `EN_CURSO` con `fechaFin <= hoy` → `FINALIZADA` y publica
  `vacaciones.finalizadas` (comparación **inclusiva**: un período con
  `fechaFin = hoy` finaliza el mismo día).

Cada evento sale con el `empleadoEmail` tomado de la réplica local (nil si el
empleado nunca llegó) y el `estado` fresco de la fila transicionada.

### Elección de precisión: fecha (opción implementada) vs fecha-hora

La comparación es por día calendario porque `fecha_inicio`/`fecha_fin` son
columnas `DATE`. La alternativa por hora exacta requeriría `TIMESTAMPTZ` y
migración de la tabla: queda como trabajo futuro (no implementado).

### Estrategia de demo (decisión del PDF)

`POST /vacaciones` con `fechaInicio = hoy` y `fechaFin = hoy`: al estar la
comparación inclusiva de ambos lados, el primer tick pasa el período a
`EN_CURSO` (y publica `vacaciones.iniciadas`) y el mismo tick o el siguiente
lo pasa a `FINALIZADA` (publica `vacaciones.finalizadas`). La vida completa
del evento queda demostrada dentro del mismo día.

### Idempotencia y limitación con N instancias

La transición es un `UPDATE ... WHERE estado = '<estado esperado>' RETURNING
*`; el evento se publica SOLO si la fila efectivamente transicionó: ticks
repetidos ya no la encuentran en el estado candidato y no duplican eventos.

Limitación conocida: sin coordinación, N instancias del servicio despertarían
y seleccionarían los mismos candidatos; el UPDATE condicional evita dobles
transiciones/eventos pero hay trabajo redundante. En el **Reto 31** se
resuelve con ShedLock (o equivalente).

## Validaciones de `POST /vacaciones` (todas responden 400 con mensaje descriptivo)

1. `fechaFin` no anterior a `fechaInicio`; el período de un solo día
   (`fechaFin == fechaInicio`) es válido (estrategia de demo del Reto 5,
   `fechaInicio=hoy/fechaFin=hoy`).
2. `fechaInicio` no anterior a hoy (fecha del servidor, comparación por fecha).
3. Sin solapamiento (rango inclusivo) con otro período del mismo empleado en
   `PROGRAMADA` o `EN_CURSO`; en conflicto la respuesta incluye la clave
   `conflicto` con el período en pugna.
4. El empleado debe existir en la réplica local (llegó `empleado.creado`) y no
   estar `RETIRADO` (llegó `empleado.retirado`).

## Eventos

- **Cola**: `q.vacaciones.empleados` (durable), enlazada al exchange topic
  durable `ecosistema.eventos` con las keys `empleado.creado` y
  `empleado.retirado`.
- **Deduplicación**: tabla `eventos_procesados(id PK, procesado_en)`; el `id`
  del envelope es la clave. Evento duplicado → ACK sin efecto.
- **ACK manual** después de persistir el efecto y la marca de dedup en la
  misma transacción. Si el proceso cae antes del ACK, el broker reentrega y
  la dedup evita el doble efecto.
- **Backoff exponencial** (2s → tope 30s) si el broker no está disponible al
  arrancar o se cae a mitad de consumo; el servicio nunca crashea por esto.
- **Publicación**: `vacaciones.programadas` con `empleadoEmail` tomado de la
  réplica local, para que Notificaciones no necesite consultar a nadie.
- **Baja por retiro**: al consumir `empleado.retirado`, además de marcar
  `RETIRADO` en la réplica, cancela a `CANCELADA` los `PROGRAMADA` con
  `fechaInicio` posterior a la `fechaRetiro` (misma transacción que la marca
  de dedup). Los `EN_CURSO` no se tocan (caso borde Reto 5) y el scheduler ya
  no los toma como candidatos porque `por_iniciar` solo mira `PROGRAMADA`.
- **Reto 5**: `vacaciones.iniciadas` (PROGRAMADA → EN_CURSO) y
  `vacaciones.finalizadas` (EN_CURSO → FINALIZADA), publicados por el
  scheduler tras la transición confirmada (mismo formato de envelope:
  `{id uuid, type, version 1.0, occurredAt UTC ISO, producer
  vacaciones-service, data:{id, empleadoId, empleadoEmail, fechaInicio,
  fechaFin, estado}}`).

## Esquema

`init.sql` (una sola vía, aplicado por `docker-entrypoint-initdb.d`) y, como
red de seguridad, el servicio aplica el mismo DDL idempotente al arrancar
(`Vacaciones::Database.ensure_schema`). Tablas: `vacaciones`,
`empleados_locales`, `eventos_procesados`.

El `estado` de `vacaciones` es `TEXT` sin CHECK: admite los 4 estados del
Reto 5 (`PROGRAMADA | EN_CURSO | FINALIZADA | CANCELADA`) sin migración;
el índice `idx_vacaciones_estado` sostiene las consultas del scheduler.

## Cómo correr

```bash
# Todo el ecosistema (desde la raíz del repo)
docker compose up --build database-vacaciones vacaciones-service message-broker

# Solo el servicio, local (requiere Postgres y RabbitMQ en localhost)
cd vacaciones && bundle install && ruby app.rb
```

## Tests

La suite corre **sin broker ni Postgres reales** (lógica pura + fakes en memoria):

```bash
cd vacaciones
ruby tests/validaciones_test.rb        # 4 validaciones + formato/ids
ruby tests/endpoints_test.rb           # endpoints + publish tras save + fallo de publish
ruby tests/consumer_publisher_test.rb  # réplica, dedup, ACK, backoff, envelope 3.8
ruby tests/scheduler_test.rb           # Reto 5: transiciones, idempotencia, envelopes iniciadas/finalizadas
```

## Cómo verificar el servicio

1. Crear un empleado en `empleados-service` y esperar el evento
   `empleado.creado` (Management UI: http://localhost:15672).
2. Verificar la réplica local:
   `docker compose exec database-vacaciones psql -U postgres -d vacaciones -c "SELECT * FROM empleados_locales"`
3. Programar vacaciones (por el gateway, puerto 8080, o dentro de la red):
   `POST /vacaciones` con `{"empleadoId":"E001","fechaInicio":"<futuro>","fechaFin":"<futuro>"}` → 201 con `V-AAAA-NNNN`.
4. Confirmar el evento `vacaciones.programadas` en la cola `q.notificaciones`.
5. Repetir el POST con fechas que se solapen → 400 con la clave `conflicto`.
6. `DELETE /vacaciones/{id}` de un período futuro → 200 con estado `CANCELADA`.
7. **Demo del ciclo de vida (Reto 5)**: crear un período con
   `fechaInicio = fechaFin = <hoy>` (formato `YYYY-MM-DD`) y esperar
   ~1-2 minutos con `SCHEDULER_INTERVAL_S=60`: el scheduler lo pasa a
   `EN_CURSO` → evento `vacaciones.iniciadas`, y luego a `FINALIZADA` →
   evento `vacaciones.finalizadas` (ver la sección Scheduler para la
   semántica de la comparación inclusiva por fecha).
