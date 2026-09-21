# vacaciones-service

Servicio **productor** del ecosistema (Reto 4 — comunicación asincrónica):

- **Expone REST** para gestionar períodos de vacaciones. El `id` lo genera el
  servidor con formato `V-AAAA-NNNN` (año actual + secuencial de 4 dígitos,
  resuelto con MAX+1 dentro de la transacción de inserción).
- **Publica** el evento `vacaciones.programadas` (catálogo 3.8) tras cada
  programación exitosa. Un fallo de publish se registra en el log y **no**
  revierte la base de datos.
- **Consume** `empleado.creado` y `empleado.retirado` (catálogos 3.1 y 3.3)
  para mantener una **réplica local de empleados** (opción b: validación por
  eventos, sin llamadas REST salientes).

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

En este reto solo existen los estados `PROGRAMADA` y `CANCELADA`.

## Validaciones de `POST /vacaciones` (todas responden 400 con mensaje descriptivo)

1. `fechaFin` posterior a `fechaInicio`.
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

## Esquema

`init.sql` (una sola vía, aplicado por `docker-entrypoint-initdb.d`) y, como
red de seguridad, el servicio aplica el mismo DDL idempotente al arrancar
(`Vacaciones::Database.ensure_schema`). Tablas: `vacaciones`,
`empleados_locales`, `eventos_procesados`.

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
