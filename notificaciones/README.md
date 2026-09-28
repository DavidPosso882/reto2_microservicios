# notificaciones-service (Reto 4 + Reto 5)

Servicio **puramente reactivo**: consume eventos de RabbitMQ, simula el envío de
notificaciones y expone su historial **solo en lectura**. No hace llamadas REST
salientes.

- **Lenguaje:** Python 3.12 (FastAPI + SQLAlchemy + pika)
- **Base de datos propia:** Postgres 16 (`database-notificaciones`)
- **Puerto interno:** 8084 (sin `ports:`; se accede vía API Gateway)

## Eventos consumidos (CATALOGO_EVENTOS.md)

| Routing key | Notificación generada |
|---|---|
| `empleado.creado` | `BIENVENIDA` (destinatario `data.email`) |
| `empleado.retirado` | `DESVINCULACION` |
| `vacaciones.programadas` | `VACACIONES` (mensaje con `fechaInicio`→`fechaFin`) |
| `usuario.creado` *(Reto 5, auth-service)* | `SEGURIDAD` (mensaje con reset token, vencimiento 30min) |
| `usuario.recuperacion` *(Reto 5, auth-service)* | `SEGURIDAD` (reset token + expiración) |
| `cuenta.desactivada` *(Reto 5, auth-service)* | `CUENTA` ("Su cuenta fue desactivada…", motivo) |
| `cuenta.activada` *(Reto 5, auth-service)* | `CUENTA` ("Su cuenta fue reactivada. ¡Bienvenido de regreso!") |
| `vacaciones.iniciadas` *(Reto 5, scheduler vacaciones)* | `VACACIONES` (período en curso) |
| `vacaciones.finalizadas` *(Reto 5, scheduler vacaciones)* | `VACACIONES` (período finalizado) |

Log de envío simulado, formato del PDF:
`[NOTIFICACIÓN] Tipo: BIENVENIDA|DESVINCULACION|VACACIONES|SEGURIDAD|CUENTA | Para: <email> | Mensaje: "..."`.
Los eventos de cuenta nunca incluyen contraseñas: el único dato sensible es el
reset token (JWT de un solo uso, vida corta), que el flujo del PDF pide
mostrar en el mensaje.

Cola durable `q.notificaciones`, exchange topic durable `ecosistema.eventos`,
bindings = los 9 routing keys de la tabla (fuente única: `TIPOS_VALIDOS` en
`app/mensajes.py`), ACK manual **después** de persistir (notificación + dedup
en `eventos_procesados`). Tipos desconocidos o payload inválido se descartan
con ACK (poison, no bloquean la cola). Si el broker no está disponible al
arrancar, reintenta con backoff exponencial sin morir.

## Endpoints (solo lectura)

- `GET /notificaciones` — todas las notificaciones.
- `GET /notificaciones/{empleadoId}` — filtradas por empleado.
- `GET /docs` — Swagger UI (OpenAPI automático de FastAPI).
- `GET /health` — healthcheck.

Respuesta camelCase: `id, tipo, destinatario, mensaje, fechaEnvio, empleadoId`.

## Variables de entorno (con defaults locales)

| Variable | Default |
|---|---|
| `PORT` | `8084` |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `localhost` / `5432` / `notificaciones` / `postgres` / `postgres` |
| `RABBITMQ_HOST` / `RABBITMQ_PORT` | `localhost` / `5672` |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | `guest` / `guest` |
| `CONSUMER_ENABLED` | `true` |
| `NOTIFICACIONES_ROOT_PATH` | `/notificaciones` (root_path ASGI tras el gateway; override para entornos sin strip, como tests) |

En `docker-compose.yml` se sobrescriben con los valores del ecosistema
(`RABBITMQ_HOST=message-broker`, credenciales `${RABBITMQ_USER:-admin}`).

## Creación de esquema (única vía)

El esquema se crea **exclusivamente con SQLAlchemy** (`Base.metadata.create_all`)
en el startup del servicio. **No existe `init.sql`** para este servicio: así las
dos vías no pueden divergir.

## Cómo correr

### Local (sin Docker)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Requiere Postgres y RabbitMQ locales, o exporta DATABASE_URL para otra BD:
export DATABASE_URL=sqlite:///./notificaciones.db   # solo para probar la API
export CONSUMER_ENABLED=false                       # sin RabbitMQ local
uvicorn app.main:app --host 0.0.0.0 --port 8084
# Swagger: http://localhost:8084/docs
```

### Docker (build aislado)

```bash
docker build -t notificaciones-service ./notificaciones
```

### Docker Compose (ecosistema completo)

```bash
docker compose up -d database-notificaciones notificaciones-service
docker compose logs -f notificaciones-service
```

### Tests (no requieren RabbitMQ ni Postgres)

```bash
cd notificaciones && python -m pytest tests -v
```

Usan SQLite en memoria y mockean todo el broker; el consumer no arranca en tests.
