# Reto 5 — Seguridad y Control de Acceso con JWT (evolución del Reto 4)

Evolución del Reto 4 (comunicación asincrónica por eventos): el sistema suma
**autenticación y autorización con JWT**. El `api-gateway` valida el token en el único
borde HTTP; los 5 servicios de negocio pasan de públicos a protegidos sin código JWT
propio; entra en vigor RBAC; el nuevo `auth-service` conduce el ciclo de vida de
cuentas. Demo end-to-end: [`GUIA_PRUEBAS_RETO5.md`](GUIA_PRUEBAS_RETO5.md).

**URL base vigente: `http://localhost:8080`** (única publicada al host, como en Reto 3).

## 1. Arquitectura (14 contenedores)

| Servicio | Lenguaje | Puerto interno | Puerto host |
|---|---|---|---|
| api-gateway | Node.js 22 + Express 4 | 8080 | **8080 (el único HTTP)** |
| auth-service (nuevo) | Node.js 22 + Express 4 | 8086 | ninguno (`expose`) |
| empleados-service | Java 21 + Spring Boot 3 | 8081 | ninguno |
| departamentos-service | Node.js 22 + Express 4 | 8082 | ninguno |
| perfiles-service | Python + FastAPI | 8083 | ninguno |
| notificaciones-service | Python + FastAPI (9 claves de entorno) | 8084 | ninguno |
| vacaciones-service | Ruby + Sinatra (scheduler integrado) | 8085 | ninguno |
| databases + `database-auth` (nueva, BD `auth_db`) | postgres:16-alpine | 5432 | ninguno |
| message-broker | RabbitMQ 3 + management | 5672 / 15672 | **5672 y 15672** |

14 en total: gateway + auth + 5 servicios de negocio + 6 postgres + rabbitmq. Solo
`:8080` como borde HTTP al host; 5672 (AMQP) y 15672 (UI) son exclusivos del broker.

## 2. Rutas del Gateway: nuevas de auth; negocio ahora protegido

| Ruta | Acceso | Destino |
|---|---|---|
| `POST /auth/bootstrap` | pública (solo si aún no hay ADMIN) | auth-service |
| `POST /auth/login` | pública | auth-service |
| `POST /auth/recover-password` | pública | auth-service |
| `POST /auth/reset-password` | pública (token de un uso) | auth-service |
| `POST /auth/change-password` | protegida (propio usuario) | auth-service |
| `GET/POST /empleados`, `/empleados/*` | **protegida** | :8081 |
| `GET/POST /departamentos`, `/departamentos/*` | **protegida** | :8082 |
| `GET/POST /perfiles`, `/perfiles/*` | **protegida** (propiedad en `PUT /perfiles/{id}`) | :8083 |
| `GET /notificaciones`, `/notificaciones/*` | **protegida** | :8084 |
| `GET/POST /vacaciones`, `/vacaciones/*` | **protegida** | :8085 |
| `GET /health` | pública | gateway |

Las 5 rutas de negocio del Reto 3 se enrutan igual; solo pasan de públicas a protegidas (`503`/`404` intactos).

## 3. Variables de entorno nuevas

| Variable | Dónde | Nota |
|---|---|---|
| `JWT_SECRET` | auth-service **y** api-gateway (misma clave) | obligatoria y fail-fast: si falta, compose aborta; generar con `openssl rand -hex 32` en `.env` |
| `AUTH_URL` | api-gateway | `http://auth-service:8086` |
| `SCHEDULER_INTERVAL_S` | vacaciones-service | segundos entre corridas del scheduler (default `60` = 1 minuto) |

## 4. Cómo obtener un token

```bash
# una sola vez: crea el primer ADMIN
curl -X POST http://localhost:8080/auth/bootstrap -H 'Content-Type: application/json' \
  -d '{"email":"admin@empresa.com","password":"Admin123!"}'

# login (emitir/renovar JWT)
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8080/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@empresa.com","password":"Admin123!"}' | jq -r .token)

# usar el token en negocios
curl http://localhost:8080/empleados -H "Authorization: Bearer $ADMIN_TOKEN"
```

Sin token: `401 {"error":"Token faltante o inválido"}`. Sin permiso: `403 {"error":"No tiene permisos para esta operación"}`.

## 5. Estrategia de validación: solo el gateway (una vez)

El gateway valida firma y expiración del JWT **una única vez** en el borde, sin
duplicar la misma lógica JWT en 4 lenguajes; prepara el Reto 10 (JWKS asimétrico).

## 6. RBAC + reglas de propiedad

| Rol | Alcance |
|---|---|
| ADMIN | todo: gestión de todos los recursos, bootstrap, consultas globales (vacaciones, notificaciones, departamentos) |
| USER | `GET` de recursos + `PUT /perfiles/{id}` **solo si es el propio** + `POST /auth/change-password` **solo para sí mismo** |

`403` cuando el rol no alcanza o la propiedad falla; se compara el `userId` del JWT con
el recurso pedido.

## 7. Scheduler del ciclo de vida (vacaciones-service)

Cada `SCHEDULER_INTERVAL_S` segundos (default `60`, 1 minuto): `PROGRAMADA → EN_CURSO`
cuando `fechaInicio <= hoy`; `EN_CURSO → FINALIZADA` cuando `fechaFin <= hoy` (fin
**inclusivo**). Demo: período `hoy–hoy` se inicia y termina con 2 corridas. Idempotente:
`UPDATE ... WHERE <estado previo> ... RETURNING id` (eventos solo por filas cambiadas).
Limitación: con **N instancias** habría eventos duplicados → se propone **ShedLock** (Reto 31).

## 8. Ciclo de vida de la cuenta (vista por eventos)

```text
empleado.creado ─► auth consume ─► usuario.creado (inactivo)
                 └─► recover/reset (token de un uso) ─► reset-password ─► activo
login (JWT) ─► uso de negocios protegidos
vacaciones.iniciadas ─► cuenta.desactivada
vacaciones.finalizadas ─► cuenta.activada
empleado.retirado ─► cuenta.desactivada (PERMANENTE)
EDGE: la cuenta retirada NO se reactiva (ni por login, ni por reset, ni re-contratación).
```

---

# Reto 3 — API Gateway y Resiliencia Sincrónica

Evolución del sistema del Reto 2 (empleados + departamentos con persistencia):
se agrega el **api-gateway** como punto de entrada único y un **Circuit Breaker**
en la llamada empleados → departamentos. Las rutas internas no cambian; solo
deja de accederse a ellas desde fuera.

**URL base del sistema (única desde este reto): `http://localhost:8080`**
— es la que usarán la suite del Reto 6 y Prometheus del Reto 8.

---

## 1. Levantar el sistema

Requisito: Docker + Docker Compose.

```bash
cp .env.example .env   # ajustar passwords si se desea (nunca commitear el .env real)
docker compose up --build -d
```

Verificado: `docker compose config` valida (exit 0) y los 5 contenedores quedan
`healthy`, con **un solo puerto publicado al host**:

```
reto2-api-gateway-1              Up (healthy)   0.0.0.0:8080->8080/tcp
reto2-database-departamentos-1   Up (healthy)   5432/tcp
reto2-database-empleados-1       Up (healthy)   5432/tcp
reto2-departamentos-service-1    Up (healthy)   8082/tcp        # sin binding al host
reto2-empleados-service-1        Up (healthy)   8081/tcp        # sin binding al host
```

---

## 2. Arquitectura: servicio ↔ lenguaje ↔ puerto

| Servicio | Lenguaje | Puerto interno | Puerto host |
|---|---|---|---|
| api-gateway | Node.js 22 + Express 4 + http-proxy-middleware 3 | 8080 | **8080 (el único)** |
| empleados-service | Java 21 + Spring Boot 3.2.5 + Resilience4j 2.2.0 | 8081 | ninguno (`expose`) |
| departamentos-service | Node.js 22 + Express 4 | 8082 | ninguno (`expose`) |
| database-empleados / database-departamentos | postgres:16-alpine | 5432 | ninguno |

Red interna: `microservices-network`. Los servicios de negocio usan `expose:`
(visibles solo dentro de la red); solo el gateway declara `ports:`.

### Tabla de rutas del Gateway (externa → interna)

| Ruta externa | Destino interno |
|---|---|
| `GET/POST /empleados`, `/empleados/*` | `http://empleados-service:8081/empleados...` |
| `GET/POST /departamentos`, `/departamentos/*` | `http://departamentos-service:8082/departamentos...` |
| `GET /health` | Propio: `{"status":"ok","service":"api-gateway"}` |

El gateway **no contiene lógica de negocio**: reenvía método, cuerpo, query,
cabeceras y código de estado intactos. Si el destino no responde, devuelve
`503 {"status":503,"error":"El servicio de ... no está disponible en este momento"}`
(nunca una página del framework). Rutas desconocidas:
`404 {"status":404,"error":"Recurso no encontrado"}` (mismo envoltorio que los servicios).

### Justificación de la tecnología del Gateway

Se pedía un **gateway de aplicación** (de código), no un enrutador declarativo,
por la trayectoria del curso: en el Reto 5 validará JWT, en el 10 validará por
JWKS y propagará identidad como cabeceras, y el proyecto final compone
respuestas — nada de eso es natural en Nginx/Traefik (Traefik llegará en el
Reto 11 como balanceador delante de este gateway). Dentro de los gateways de
aplicación se eligió **Node.js + Express + http-proxy-middleware** porque el
equipo ya opera Express en departamentos-service (mismo modelo mental, mismo
Dockerfile, imagen pequeña), y el proxy por prefijo con `pathRewrite` mantiene
las rutas internas byte a byte. Spring Cloud Gateway era la alternativa, pero
duplicaba peso (JVM extra) sin aportar nada que este reto necesite.

---

## 3. Endpoints (todos por el Gateway)

### Departamentos

| Método | Ruta | Éxito | Error |
|---|---|---|---|
| POST | `/departamentos` `{id, nombre, descripcion}` | 201 objeto creado | 400 (campos faltantes / id duplicado) |
| GET | `/departamentos/{id}` | 200 objeto | 404 `{"status":404,"error":"..."}` |
| GET | `/departamentos` | 200 arreglo | — |

### Empleados

| Método | Ruta | Éxito | Error |
|---|---|---|---|
| POST | `/empleados` (modelo canónico, 10 campos) | **201** con `estado: ACTIVO` (o `PENDIENTE_VALIDACION` en fallback) | 400 (duplicados, validación, depto inexistente) |
| GET | `/empleados/{id}` | 200 objeto | 404 |
| GET | `/empleados` | 200 arreglo | — |
| GET | `/empleados/circuit/state` | 200 `{"nombre","estado","tasaFallosPorcentaje","llamadasExitosas","llamadasFallidas","llamadasBloqueadas"}` | — |
| POST | `/empleados/{id}/revalidar` | 200 empleado reconciliado a `ACTIVO` (idempotente si ya lo estaba) | 400 (depto inexistente), 404 (empleado inexistente), 503 (sigue caído o circuito abierto) |

Notas:

- Validaciones del registro en orden: 1) unicidad `id`, 2) unicidad `email`,
  3) unicidad `numeroEmpleado`, 4) existencia del `departamentoId` (REST a
  departamentos). El 404 de negocio es definitivo y **no abre el circuito**.
- El campo `mensaje` solo aparece en la respuesta 201 del fallback
  (`@Transient`: no se persiste, no cambia ningún contrato del Reto 2).

---

## 4. Circuit Breaker

### Parámetros elegidos y por qué

| Parámetro | Valor | Por qué |
|---|---|---|
| Ventana / umbral | 5 llamadas, 50 % de fallos (se abre con 5 fallos consecutivos) | Dentro del rango sugerido (3-5); con 5 hay evidencia clara antes de degradar |
| Espera en OPEN | 30 s | Extremo bajo del rango (30-60 s): la demo muestra recuperación sin esperas eternas |
| Prueba en HALF_OPEN | 1 llamada, transición automática | Si departamentos volvió, se cierra solo; si no, se reabre sin reiniciar nada |
| Qué cuenta como fallo | Solo `DepartamentoNoDisponibleException` | Un 404 es negocio, no caída; librería Resilience4j (programático, sin AOP, para no cambiar el constructor del servicio) |

El estado es observable sin herramientas extra:
`GET /empleados/circuit/state` → `{"nombre":"departamentos","estado":"OPEN",...}`.

### Estrategia de fallback: disponibilidad con reconciliación

Se eligió **aceptar con `estado: PENDIENTE_VALIDACION`** en lugar de rechazar
con 503. Justificación de negocio: si departamentos cae diez minutos, RRHH no
puede quedar parado diez minutos; se prefiere disponibilidad y se paga con una
reconciliación explícita. Nunca se acepta con un departamento por defecto
(eso inventa datos). La reconciliación es real, no un documento:
`POST /empleados/{id}/revalidar` revalida contra departamentos y flips a
`ACTIVO` (o rechaza con 400 si el departamento no existe). Es la misma tensión
disponibilidad-vs-consistencia que reaparecerá en el Reto 4 (async) y el 12 (Saga).

### Cómo reproducir la prueba del Circuit Breaker

```bash
# 1. Sistema sano: crear un departamento
curl -X POST http://localhost:8080/departamentos \
  -H "Content-Type: application/json" \
  -d '{"id":"IT","nombre":"Tecnologia","descripcion":"Departamento de TI"}'

# 2. Tumbar departamentos
docker compose stop departamentos-service

# 3. Registrar empleados y OBSERVAR EL TIEMPO de cada uno
for i in {1..8}; do
  echo "--- Petición $i ---"
  time curl -s -X POST http://localhost:8080/empleados \
    -H "Content-Type: application/json" \
    -d '{"id":"E00'$i'","nombre":"Test '$i'","apellido":"CB","email":"cb'$i'@empresa.com","numeroEmpleado":"EMP-CB-00'$i'","cargo":"Tester","area":"Tecnologia","departamentoId":"IT","fechaIngreso":"2026-03-01"}'
done
# Esperado: las primeras 5 tardan ~15 s (timeout 2 s x 4 intentos + backoff 1+2+4 s,
# circuito CLOSED); desde la 6.ª responden en ~0,02 s con PENDIENTE_VALIDACION
# (circuito OPEN, sin tocar la red). Verificar:
curl http://localhost:8080/empleados/circuit/state   # {"estado":"OPEN",...}

# 4. Restaurar y esperar el timeout del circuito (30 s)
docker compose start departamentos-service
sleep 35

# 5. Recuperación automática: un depto inexistente debe dar 400
#    (solo una consulta REAL a departamentos puede responder 400)
curl -X POST http://localhost:8080/empleados \
  -H "Content-Type: application/json" \
  -d '{"id":"E100","nombre":"Recuperado","apellido":"Test","email":"rec@empresa.com","numeroEmpleado":"EMP-100","cargo":"Tester","area":"Tecnologia","departamentoId":"NO-EXISTE","fechaIngreso":"2026-03-01"}'
# → {"status":400,"error":"El departamento con id 'NO-EXISTE' no existe"}

# 6. Reconciliar un pendiente aceptado durante la caída
curl -X POST http://localhost:8080/empleados/E001/revalidar
# → 200 con "estado":"ACTIVO"
```

### Verificar el punto de entrada único y el 503 del Gateway

```bash
curl http://localhost:8080/departamentos   # 200 por el Gateway
curl http://localhost:8080/empleados       # 200 por el Gateway
curl http://localhost:8080/health          # {"status":"ok","service":"api-gateway"}
curl --max-time 5 http://localhost:8081/departamentos
# → curl exit 7 (conexión rechazada): ningún microservicio publica puertos

docker compose stop departamentos-service
curl -i http://localhost:8080/departamentos
# → 503 {"status":503,"error":"El servicio de departamentos no está disponible en este momento"}
docker compose start departamentos-service
```

---

## 5. Tests y evidencias

- `empleados`: `mvn test` → **Tests run: 38, Failures: 0, Errors: 0**
  (28 del Reto 2 + 7 nuevos del circuito/fallback/revalidar + 3 actualizados al
  fallback; H2 en tests, departamentos stubbeado).
- `api-gateway`: `npm test` → **7 pass, 0 fail** (node:test con upstreams
  falsos: enrutamiento, propagación de cuerpo/cabeceras/estado, 503 con destino
  caído, 404 propio, `/health`).
- `departamentos`: sin cambios de código en este reto (`npm test` igual que Reto 2).
- Colección Bruno actualizada a la URL base única: `evidencias/bruno/Reto3/`
  (variable `{{gateway_url}}` + requests de `/health`, `/circuit/state` y `/revalidar`).
- `evidencias/reto3/circuit-breaker.log`: salida del bucle de 8 peticiones con
  el salto 15 s → 0,02 s y el estado `OPEN` (`tasaFallosPorcentaje: 100.0`,
  `llamadasFallidas: 5`, `llamadasBloqueadas: 3`).

## 6. Estructura del repo

```
.
├── docker-compose.yml          # gateway con ports:; negocio con expose:
├── api-gateway/                # Node Express (nuevo Reto 3): src/app.js (fábrica
│   │                           # testeable), src/server.js, test/, Dockerfile
├── empleados/                  # Java Spring Boot + Resilience4j (programático)
│   └── src/main/.../config/DepartamentoCircuitBreaker.java  # parámetros (nuevo)
│   └── .../service/EmpleadoService.java  # fallback PENDIENTE + revalidar + estado
│   └── .../controller/EmpleadoController.java  # + /circuit/state, /{id}/revalidar
├── departamentos/              # Node Express (sin cambios de código)
└── evidencias/bruno/Reto3/     # colección contra {{gateway_url}}
```

## 7. Decisiones heredadas del Reto 2 (sin cambios)

PostgreSQL 16 en ambos servicios (una BD por servicio, sin accesos cruzados);
esquema vía `init.sql` (`ddl-auto=none`); unicidad con pre-validación + `UNIQUE`
en BD; timeout 2 s + 3 reintentos con backoff 1 s → 2 s → 4 s hacia
departamentos (el Breaker los envuelve, no los reemplaza).

---

# Reto 4 — Comunicación Asincrónica y Eventos

Evolución del Reto 3: se agrega **RabbitMQ** como message broker y tres servicios
nuevos — **perfiles** (Go), **notificaciones** (Python) y **vacaciones** (Ruby) —
que se integran al ecosistema por **eventos**, no por llamadas REST. Empleados pasa
a publicar eventos y vacaciones valida la existencia del empleado contra una
**réplica local** alimentada por eventos. El gateway suma las rutas
`/perfiles`, `/notificaciones` y `/vacaciones`; la URL base única sigue siendo
`http://localhost:8080`.

Contrato normativo de eventos: **`CATALOGO_EVENTOS.md`** (envelope, payloads,
exchange, colas y deduplicación).

## 8. Broker: RabbitMQ

Se eligió **RabbitMQ** (`rabbitmq:3-management`) sobre Kafka, Redis Streams y NATS:

- **Fan-out con exchanges topic**: cada consumer declara su propia cola durable y la
  enlaza solo a las routing keys que le interesan; el fan-out sale gratis sin
  repetir lógica de despacho (con Kafka cada consumer gestionaría offsets y con
  NATS sería at-least-once puro sin cola durable por servicio).
- **Management UI incluida** (`http://localhost:15672`): ver colas, consumers,
  mensajes en vuelo y publicar manualmente fue clave para depurar y para la
  evidencia de deduplicación.
- **Peso operativo**: un solo contenedor, sin zookeeper/cluster; adecuado para un
  ecosistema de 5 servicios con volúmenes de mensaje modestos.
- **Ejemplo del enunciado**: la consigna orienta hacia RabbitMQ, y nada del
  dominio (eventos de dominio simples, no streams de alta tasa) pide algo más.

| Puerto | Uso | Publicación |
|---|---|---|
| 5672 | AMQP (productores/consumidores) | al host (para pruebas manuales) |
| 15672 | Management UI | al host |

Las credenciales se configuran por variables de entorno (`RABBITMQ_USER` /
`RABBITMQ_PASSWORD` en `.env`; el servicio declara `RABBITMQ_DEFAULT_USER/PASS` y
todos los servicios cliente reciben las mismas por `environment`).

## 9. Arquitectura: servicio ↔ lenguaje ↔ puerto

| Servicio | Lenguaje | Puerto interno | Puerto host |
|---|---|---|---|
| api-gateway | Node.js 22 + Express 4 + http-proxy-middleware 3 | 8080 | **8080 (el único)** |
| empleados-service | Java 21 + Spring Boot 3.2.5 | 8081 | ninguno (`expose`) |
| departamentos-service | Node.js 22 + Express 4 | 8082 | ninguno (`expose`) |
| perfiles-service | **Go 1.26** (stdlib `net/http` + amqp091-go) — nuevo | 8083 | ninguno (`expose`) |
| notificaciones-service | **Python 3.12** (FastAPI + SQLAlchemy + pika) — nuevo | 8084 | ninguno (`expose`) |
| vacaciones-service | **Ruby 3.3** (Sinatra + bunny) — nuevo | 8085 | ninguno (`expose`) |
| message-broker | RabbitMQ 3-management (infraestructura) | 5672 / 15672 | 5672 y 15672 |

Cinco lenguajes efectivos de negocio: **Java, Node.js, Python, Go y Ruby**.
Se mantiene la política del Reto 3: todos los servicios de negocio usan
`expose:` (visibles solo dentro de `microservices-network`); solo el gateway
publica `ports:` al host en 8080 (y el broker, que es infraestructura de
observabilidad, en 5672/15672). Cada servicio nuevo tiene su **BD Postgres 16
propia** (`database-perfiles`, `database-notificaciones`, `database-vacaciones`),
sin accesos cruzados.

## 10. Despliegue

```bash
cp .env.example .env   # ajustar passwords si se desea (nunca commitear el .env real)
docker compose up --build -d
```

Verificación (evidencia completa: `evidencias/reto4/flujo-e2e.log`, run final
con **12/12 contenedores healthy**):

```bash
docker compose ps                          # 12 contenedores Up (healthy)
# Management UI: http://localhost:15672 (admin / valor de RABBITMQ_PASSWORD)
# Queues: q.perfiles, q.notificaciones, q.vacaciones.empleados (1 consumer cada una)
curl http://localhost:8080/health          # {"status":"ok","service":"api-gateway"}
```

## 11. Eventos del ecosistema

Exchange topic durable **`ecosistema.eventos`**, routing key = `type` del evento,
cola durable por servicio consumer, ACK manual después de persistir y
**deduplicación por `id` del envelope** (tabla `eventos_procesados(id PK)`).
Detalles y payloads exactos: `CATALOGO_EVENTOS.md`.

| Evento (`type`) | Productor | Consumidores (cola) | Efecto |
|---|---|---|---|
| `empleado.creado` | empleados | notificaciones (`q.notificaciones`), perfiles (`q.perfiles`), vacaciones (`q.vacaciones.empleados`) | BIENVENIDA · perfil por defecto · alta en réplica local |
| `empleado.actualizado` | empleados | perfiles (`q.perfiles`) | sincroniza nombre/apellido/email (nunca pisa contacto propio) |
| `empleado.retirado` | empleados | notificaciones, perfiles, vacaciones | DESVINCULACIÓN · `archivado=true` (jamás borra) · baja en réplica local |
| `vacaciones.programadas` | vacaciones | notificaciones (`q.notificaciones`) | notificación `VACACIONES` (incluye `empleadoEmail` desnormalizado) |

El envelope común lleva `id` (UUID v4, **clave de dedup**), `type`, `version`,
`occurredAt`, `producer` y `data` (foto completa del empleado; los consumers son
idempotentes y no dependen del orden).

## 12. Decisión validación-4: réplica local por eventos (opción b)

Vacaciones valida la existencia y el estado del empleado contra una **réplica
local** (`empleados_locales`) alimentada por los eventos
`empleado.creado` / `empleado.retirado`, en lugar de consultar REST a
empleados-service.

- **Por qué**: autonomía total (cero llamadas REST salientes en el camino de
  validación), disponibilidad si empleados cae (el flujo de vacaciones no se
  degrada) y coherencia con el espíritu async del reto: si todo se resuelve por
  REST, la mensajería queda cosmética.
- **Costo aceptado**: **consistencia eventual** — la réplica solo sabe lo que
  llegó por eventos. Si se programa vacaciones para un empleado cuyo evento
  todavía no llegó, responde `400 "no existe en la réplica local (aún no llegó
  el evento empleado.creado)"`.
- **Consecuencia observada**: por semántica pub/sub, los eventos publicados
  **antes** de que una cola exista/enlace se pierden para ese consumer (no hay
  replay). Se manifestó en el flujo e2e (evento de E001 perdido por race de
  topología al arranque, `flujo-e2e.log` paso 3c). Para vaciar el sistema:
  recrear volúmenes (`docker compose down -v`) o republicar manualmente vía
  Management API.

## 13. Evidencia de deduplicación

`evidencias/reto4/dedup.log`: se publicó **dos veces el mismo envelope** (mismo
`id` `22222222-…`, evento `empleado.creado` de `EDEDUP`) vía Management API.
Resultado esperado y observado: `{"routed":true}` en ambos publishes, **1 solo
perfil** en `GET /perfiles/EDEDUP` (200, sin duplicados), **1 sola BIENVENIDA**
en `GET /notificaciones/EDEDUP` y **1 fila** en `eventos_procesados` por
servicio consumer. El segundo mensaje se ACKea sin efecto.

Reproducción vía Management API (publicar el MISMO payload dos veces):

```bash
BODY='{"properties":{"content_type":"application/json"},"routing_key":"empleado.creado","payload":{"id":"22222222-2222-4222-8222-222222222222","type":"empleado.creado","version":"1.0","occurredAt":"2026-09-21T17:34:00Z","producer":"empleados-service","data":{"id":"EDEDUP","nombre":"Dedup","apellido":"Test","email":"dedup.test@empresa.com","numeroEmpleado":"NUM-DUP","cargo":"QA","area":"IT","departamentoId":"IT","fechaIngreso":"2026-04-01","estado":"ACTIVO"}},"payload_encoding":"string"}'

curl -u admin:$RABBITMQ_PASSWORD -X POST \
  http://localhost:15672/api/exchanges/%2F/ecosistema.eventos/publish \
  -H 'Content-Type: application/json' \
  -d "$BODY"
# → {"routed":true}  — repetir idéntico y verificar 1 perfil / 1 BIENVENIDA / 1 fila de dedup
```

## 14. Cómo probar el flujo (todo por el gateway :8080)

Secuencia mínima (evidencia completa con salidas reales:
`evidencias/reto4/flujo-e2e.log`):

```bash
# 1. Departamento                          → 201 (400 si ya existe)
curl -X POST http://localhost:8080/departamentos -H 'Content-Type: application/json' \
  -d '{"id":"IT","nombre":"Tecnologia","descripcion":"Departamento de TI"}'

# 2. Empleado (dispara empleado.creado)    → 201 estado ACTIVO
curl -X POST http://localhost:8080/empleados -H 'Content-Type: application/json' \
  -d '{"id":"E100","nombre":"Juan","apellido":"Perez","email":"juan.perez@empresa.com",
  "numeroEmpleado":"NUM-100","cargo":"Developer","area":"IT","departamentoId":"IT",
  "fechaIngreso":"2026-03-01"}'

# 3. Esperar el consumo async (~15 s, backoff de topología al arranque)
sleep 15

# 4. Perfil creado por evento              → 200 (perfil por defecto)
curl http://localhost:8080/perfiles/E100
# 5. Notificación de bienvenida            → 200 (1 BIENVENIDA)
curl http://localhost:8080/notificaciones/E100
# 6. Actualizar contacto propio del perfil → 200 (ignora campos de identidad)
curl -X PUT http://localhost:8080/perfiles/E100 -H 'Content-Type: application/json' \
  -d '{"telefono":"+54-11-5555-1234","ciudad":"Buenos Aires","biografia":"Backend dev"}'

# 7. Vacaciones (valida contra la réplica local; dispara vacaciones.programadas)
curl -X POST http://localhost:8080/vacaciones -H 'Content-Type: application/json' \
  -d '{"empleadoId":"E100","fechaInicio":"2026-12-15","fechaFin":"2026-12-30"}'   # → 201 V-AAAA-NNNN
curl http://localhost:8080/notificaciones/E100                                   # ahora también 1 VACACIONES

# 8. Validaciones 400 de vacaciones
curl -X POST http://localhost:8080/vacaciones -H 'Content-Type: application/json' \
  -d '{"empleadoId":"E100","fechaInicio":"2027-01-10","fechaFin":"2027-01-05"}'   # → 400 fechas incoherentes
curl -X POST http://localhost:8080/vacaciones -H 'Content-Type: application/json' \
  -d '{"empleadoId":"E100","fechaInicio":"2026-12-20","fechaFin":"2027-01-05"}'   # → 400 con clave "conflicto"
curl -X POST http://localhost:8080/vacaciones -H 'Content-Type: application/json' \
  -d '{"empleadoId":"E999","fechaInicio":"2027-01-10","fechaFin":"2027-01-20"}'   # → 400 no está en la réplica local

# 9. Retiro (baja lógica; dispara empleado.retirado) → 200 estado RETIRADO + fechaRetiro
curl -X DELETE http://localhost:8080/empleados/E100
curl 'http://localhost:8080/empleados?estado=RETIRADO'                            # → 200 lo lista
curl http://localhost:8080/notificaciones/E100                                    # + DESVINCULACION
curl http://localhost:8080/perfiles/E100                                          # archivado=true
curl 'http://localhost:8080/vacaciones?empleadoId=E100'                           # períodos conservados para auditoría

# 10. Auditoría de dedup (ledger por servicio, 1 fila por evento único)
docker compose exec database-perfiles psql -U postgres -d perfiles \
  -c 'SELECT * FROM eventos_procesados'
docker compose exec database-vacaciones psql -U postgres -d vacaciones \
  -c 'SELECT * FROM empleados_locales'   # réplica local
```

## 15. Tests por servicio

Todos corren **sin broker ni Postgres reales** (fakes en memoria):

| Servicio | Comando | Resultado |
|---|---|---|
| empleados | `cd empleados && mvn test` | **72 tests** (38 del Reto 3 + nuevos de eventos/PUT/DELETE/filtros) |
| api-gateway | `cd api-gateway && npm test` | **13 tests** (7 del Reto 3 + 3 rutas nuevas y propagación) |
| departamentos | `cd departamentos && npm test` | sin cambios de código en este reto |
| perfiles | `cd perfiles && go test ./...` | **22 tests** |
| notificaciones | `cd notificaciones && python -m pytest tests -v` | **30 tests** |
| vacaciones | `cd vacaciones && ruby tests/validaciones_test.rb && ruby tests/endpoints_test.rb && ruby tests/consumer_publisher_test.rb` | **29 tests** |

## 16. Estructura del repo (novedades del Reto 4)

```
.
├── CATALOGO_EVENTOS.md         # contrato normativo de eventos (envelope, colas, dedup)
├── docker-compose.yml          # + message-broker (RabbitMQ), 3 servicios y 3 BD nuevas
├── notificaciones/             # Python FastAPI + pika: consumer reactivo, solo lectura
├── perfiles/                   # Go stdlib: consumer + REST de perfiles
├── vacaciones/                 # Ruby Sinatra: CRUD + réplica local + publish
├── empleados/                  # + publish de 3 eventos, PUT/DELETE, filtros
├── api-gateway/                # + rutas /perfiles /notificaciones /vacaciones
└── evidencias/reto4/           # flujo-e2e.log, dedup.log, informe de re-verificación
```
