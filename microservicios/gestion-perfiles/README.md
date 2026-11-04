# perfiles-service

Servicio híbrido del ecosistema (Reto 4 — comunicación asincrónica):

- **Consume** eventos `empleado.creado`, `empleado.actualizado` y `empleado.retirado`
  (exchange topic durable `ecosistema.eventos`, cola durable `q.perfiles`) para crear,
  sincronizar y archivar perfiles. ACK manual **después** de persistir y deduplicación
  obligatoria por `id` del envelope (tabla `eventos_procesados`).
- **Expone REST** para consultar perfiles y actualizar los campos propios
  (`telefono`, `direccion`, `ciudad`, `biografia`). Los campos de identidad
  (`nombre`, `apellido`, `email`) solo se sincronizan por eventos.

Contrato normativo: `CATALOGO_EVENTOS.md` en la raíz del repositorio.

## Stack

- Go 1.26, `net/http` stdlib (sin frameworks), `github.com/rabbitmq/amqp091-go`, `github.com/lib/pq`.
- Postgres 16 (BD propia: `perfiles`, contenedor `database-perfiles`).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Health check propio: `{"status":"ok","service":"perfiles-service"}` |
| GET | `/openapi.yaml` | Especificación OpenAPI servida por el propio servicio |
| GET | `/perfiles` | Lista todos los perfiles (200, arreglo) |
| GET | `/perfiles/{empleadoId}` | Perfil por empleado (200 / 404) |
| PUT | `/perfiles/{empleadoId}` | Actualiza `telefono`/`direccion`/`ciudad`/`biografia` (200 / 404; ignora campos de identidad) |

Errores con el envoltorio del ecosistema: `{"status":404,"error":"El perfil del empleado 'E999' no existe"}`.

## Eventos consumidos (cola `q.perfiles`)

| Routing key | Efecto |
|---|---|
| `empleado.creado` | Perfil por defecto: nombre/apellido/email del `data`, contacto vacío. Si ya existe → upsert seguro, no duplica. |
| `empleado.actualizado` | Sincroniza SOLO `nombre`/`apellido`/`email` (nunca pisa contacto). Si no hay perfil → lo crea (tolerancia al desorden). No desarchiva perfiles. |
| `empleado.retirado` | `archivado=true` (jamás borra). Si no hay perfil → lo crea archivado. |

Deduplicación: `id` del envelope repetido → ACK sin efecto. El efecto y la marca de
dedup se persisten en **la misma transacción**.

## Configuración (variables de entorno, con defaults locales)

| Variable | Default | Descripción |
|---|---|---|
| `PORT` | `8083` | Puerto HTTP |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `localhost/5432/perfiles/postgres/postgres` | Postgres |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | URL AMQP (si está seteada, gana) |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` / `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | `localhost/5672/guest/guest` | Alternativa para armar la URL (Docker: `message-broker` + `admin/admin`) |

## Cómo correr

### Con Docker (recomendado)

```bash
docker compose up -d --build database-perfiles perfiles-service message-broker
docker compose logs -f perfiles-service
```

El esquema se crea solo: `init.sql` se monta en `docker-entrypoint-initdb.d/` y, además,
el servicio aplica el mismo DDL idempotente al arrancar (`EnsureSchema`), una sola vía.

### Local (sin Docker)

```bash
cd perfiles
go run ./cmd/perfiles-service   # requiere Postgres y RabbitMQ en localhost
```

Nota: el binario lee `openapi.yaml` del directorio de trabajo (en Docker está en `/app`).

## Cómo probar

```bash
# Health y OpenAPI
curl http://localhost:8083/health
curl http://localhost:8083/openapi.yaml

# Consulta
curl http://localhost:8083/perfiles
curl http://localhost:8083/perfiles/E001

# Actualización de contacto (identidad ignorada)
curl -X PUT http://localhost:8083/perfiles/E001 \
  -H 'Content-Type: application/json' \
  -d '{"telefono":"+54 11 4444-5555","ciudad":"Buenos Aires","biografia":"Backend dev"}'
```

Flujo end-to-end: crear un empleado con `POST /empleados` (empleados-service publica
`empleado.creado`) → el perfil aparece en `GET /perfiles`. Retirarlo con
`DELETE /empleados/{id}` → `archivado: true`.

## Tests

```bash
go test ./...
```

22 tests en verde **sin** RabbitMQ ni Postgres reales: store en memoria (`store.MemoryStore`)
que replica la semántica de Postgres, y un `Acknowledger` falso de AMQP para verificar
ACK/NACK. `openapi.yaml` se versiona en este directorio y el servicio lo sirve en `/openapi.yaml`.
