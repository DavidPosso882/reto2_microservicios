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
