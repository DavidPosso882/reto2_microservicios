# Guía: RabbitMQ

Volver al [README](../../README.md) · Eventos: [eventos.md](../eventos.md)

## 1. Acceso

| Elemento | Valor |
|---|---|
| Management UI | http://localhost:15672 |
| Usuario | `RABBITMQ_USER` del `.env` (por defecto `admin`) |
| Contraseña | `RABBITMQ_PASSWORD` del `.env` (la genera `scripts/setup-secrets.sh`) |
| AMQP | `localhost:5672` (dentro de la red: `message-broker:5672`) |

La imagen `rabbitmq:3-management` crea el usuario con `RABBITMQ_DEFAULT_USER`
y `RABBITMQ_DEFAULT_PASS` **solo la primera vez** que se inicializa el volumen
`vol-rabbitmq`; cambiar el `.env` después no cambia la contraseña (ver
[rotación](secretos.md#4-rotación)).

## 2. Topología

No hay nada que crear a mano: cada servicio declara al arrancar el exchange
`ecosistema.eventos` (topic, durable) y, si consume, su cola durable con sus
bindings. En la UI:

- **Exchanges** → `ecosistema.eventos` → *Bindings*: las 4 colas y sus claves.
- **Queues**: `q.auth`, `q.perfiles`, `q.notificaciones`,
  `q.vacaciones.empleados`, cada una con 1 consumidor. Mensajes acumulados en
  *Ready* indican un consumidor caído o lento.

Los servicios reintentan la conexión al broker con backoff (y compose
espera a que RabbitMQ esté *healthy*), así que el orden de arranque no importa.

## 3. Publicar un evento a mano (prueba de deduplicación)

*Exchanges* → `ecosistema.eventos` → *Publish message*, con routing key
`empleado.creado` y un envelope con `id` fijo. Publicarlo dos veces y
comprobar que el efecto ocurre una sola vez (un perfil, una notificación).
Por API:

```bash
curl -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" -X POST \
  http://localhost:15672/api/exchanges/%2F/ecosistema.eventos/publish \
  -H 'Content-Type: application/json' \
  -d '{"properties":{"content_type":"application/json"},"routing_key":"empleado.creado","payload":"<envelope JSON>","payload_encoding":"string"}'
```

Ejemplo completo del envelope:
[historial-retos.md § Evidencia de deduplicación](../historial-retos.md#13-evidencia-de-deduplicación).
