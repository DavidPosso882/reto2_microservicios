# Reto 2 — Orquestación de Servicios y Persistencia de Datos

Sistema de dos microservicios (empleados + departamentos), cada uno con su base de datos
PostgreSQL propia, orquestados con Docker Compose. Evolución del Reto 1 (el código del
Reto 1 quedó intacto en `reto1/`; todo lo de este reto vive en `reto2/`).

---

## 1. Levantar el sistema desde cero

Requisito: Docker + Docker Compose. Clonar el repo, entrar a `reto2/` y:

```bash
cp .env.example .env   # ajustar passwords si se desea (nunca commitear el .env real)
docker compose up --build
```

Detener conservando datos / destruir incluyendo datos:

```bash
docker compose down     # conserva volúmenes: los datos sobreviven
docker compose down -v  # elimina volúmenes: los datos se pierden
```

Verificado: `docker compose config` valida (exit 0) y `docker compose up --build -d`
deja los 4 contenedores `healthy` en ~20 s (ver §5).

---

## 2. Tabla servicio ↔ lenguaje ↔ base de datos ↔ puerto

| Servicio | Lenguaje | Motor BD | Puerto host | Puerto interno |
|---|---|---|---|---|
| empleados-service | Java 21 + Spring Boot 3.2.5 | PostgreSQL 16 (`database-empleados`) | 8080 | 8080 |
| departamentos-service | Node.js 22 + Express 4 | PostgreSQL 16 (`database-departamentos`) | 8081 | 8081 |
| database-empleados | — | postgres:16-alpine | no publicado | 5432 |
| database-departamentos | — | postgres:16-alpine | no publicado | 5432 |

Red interna: `microservices-network`. Volúmenes: `vol-empleados`, `vol-departamentos`.
Dentro de la red, empleados llama a departamentos por
`http://departamentos-service:8081` (nombre de servicio, no `localhost`).

---

## 3. Endpoints

### Departamentos (`:8081`)

| Método | Ruta | Éxito | Error |
|---|---|---|---|
| POST | `/departamentos` `{id, nombre, descripcion}` | 201 objeto creado | 400 `{"status":400,"error":"..."}` (campos faltantes / id duplicado) |
| GET | `/departamentos/{id}` | 200 objeto | 404 `{"status":404,"error":"El departamento con id {id} no existe"}` |
| GET | `/departamentos` | 200 arreglo (vacío `[]` si no hay) | — |

### Empleados (`:8080`)

| Método | Ruta | Éxito | Error |
|---|---|---|---|
| POST | `/empleados` (modelo canónico, 10 campos) | **201** objeto con `estado: ACTIVO` | 400 envoltorio (duplicados, validación, depto inexistente) |
| GET | `/empleados/{id}` | 200 objeto | 404 `{"status":404,"error":"El empleado con id {id} no existe"}` |
| GET | `/empleados` | 200 arreglo | — |

Notas:

- **POST /empleados ahora responde 201** (en el Reto 1 era 200).
- Validaciones en orden: 1) unicidad `email`, 2) unicidad `numeroEmpleado`,
  3) existencia del `departamentoId` (llamada REST a departamentos). Las tres
  rechazan con `400` y envoltorio `{"status","error"}`.
- Si departamentos no responde tras los reintentos, el registro se **rechaza**
  (400/503 con envoltorio); nunca se acepta como pendiente.
- El campo del modelo es **`area`** (ej. `"Tecnologia"`) y **`departamentoId`**
  (ej. `"IT"`); no existe ningún campo `departamentoNombre`.
- Todos los errores, en ambos servicios, usan el envoltorio
  `{"status": <código>, "error": "<mensaje en español>"}` con
  `Content-Type: application/json`.

---

## 4. Swagger / OpenAPI

- Empleados: `http://localhost:8080/swagger-ui.html` (responde 302 → 200).
- Departamentos: `http://localhost:8081/api-docs` (responde 301 → `/api-docs/` → 200,
  Swagger UI HTML).

---

## 5. Evidencias de verificación

Suite unitaria/integración: `mvn test` en `empleados` →
**Tests run: 28, Failures: 0, Errors: 0** (BUILD SUCCESS, H2 en tests, llamada a
departamentos stubbeada). `npm test` en `departamentos` →
**11 tests, 10 pass, 0 fail, 1 skip** (el skip es el test de integración con
Postgres real, que requiere `DB_*` en el host; exit 0).

Arranque ordenado (`docker compose ps` tras `up --build` desde cero):

```
reto2-database-departamentos-1   Up (healthy)   5432/tcp
reto2-database-empleados-1       Up (healthy)   5432/tcp
reto2-departamentos-service-1    Up (healthy)   0.0.0.0:8081->8081/tcp
reto2-empleados-service-1        Up (healthy)   0.0.0.0:8080->8080/tcp
```

Logs limpios: `HikariPool-1 - Start completed`, `Tomcat started on port 8080`,
`Started GestionEmpleadosApplication`, `Departamentos service listening on
http://localhost:8081`; cero líneas de error/conexión en ambos servicios.

Persistencia (verificado con `curl` antes/después):

```bash
docker compose down        # conserva volúmenes
docker compose up -d
curl http://localhost:8080/empleados/E001   # 200: el empleado sigue existiendo

docker compose down -v     # elimina volúmenes
docker compose up --build -d
curl http://localhost:8080/empleados/E001   # 404 {"status":404,...}: datos perdidos
```

Flujo de prueba sugerido (ver §3 para los cuerpos):

```bash
curl -X POST http://localhost:8081/departamentos -H "Content-Type: application/json" \
  -d '{"id":"IT","nombre":"Tecnologia","descripcion":"Departamento de TI"}'   # 201
curl -X POST http://localhost:8080/empleados -H "Content-Type: application/json" \
  -d '{"id":"E001","nombre":"Juan","apellido":"Perez","email":"juan.perez@empresa.com","numeroEmpleado":"EMP-2026-001","cargo":"Desarrollador Senior","area":"Tecnologia","departamentoId":"IT","fechaIngreso":"2026-02-10"}'  # 201
curl http://localhost:8080/empleados/E001   # 200 con estado ACTIVO
```

---

## 6. Decisiones técnicas justificadas

1. **Motor de base de datos por servicio: el mismo (PostgreSQL 16 en ambos).**
   La persistencia políglota (ej. Postgres + Mongo) es una ventaja teórica de los
   microservicios, pero duplica lo que el equipo debe saber operar (backups,
   monitoreo, healthchecks distintos, drivers distintos) a cambio de cero
   beneficio aquí: ambos servicios guardan datos relacionales simples sin
   requisitos de documentos ni de escala que justifiquen otro motor. Se eligió
   minimizar costo operativo; el desacople se mantiene igual (una BD por
   servicio, sin accesos cruzados).

2. **Creación del esquema: script `init.sql` por servicio.**
   Montado en `/docker-entrypoint-initdb.d/01-init.sql:ro`, crea tabla +
   restricciones `UNIQUE`. Es simple, explícito y reproducible con un solo
   comando. Limitación conocida y aceptada: solo se ejecuta con el volumen
   vacío; si el esquema cambia con datos existentes hay que borrar el volumen
   (`down -v`, perdiendo datos). Auto-DDL del ORM se descartó (cómodo pero
   peligroso en producción: puede alterar columnas con datos) y las migraciones
   versionadas (Flyway/Liquibase) se verán en el Reto 32; para este reto serían
   sobredimensionadas.

3. **Garantía de unicidad: consulta previa + restricción `UNIQUE` en la BD.**
   Solo consultar-antes-de-insertar deja una ventana de carrera (dos POST
   concurrentes con el mismo email la atraviesan; demostrado empíricamente en el
   Reto 1). Solo la restricción `UNIQUE` es la garantía real, pero su error nativo
   no es descriptivo. La combinación da ambas cosas: la app valida primero para
   mensajes claros (`El email '...' ya está registrado`) y la BD impone la
   invariante aunque dos peticiones lleguen al mismo tiempo.

---

## 7. Estructura del repo

```
reto2/
├── docker-compose.yml
├── .env.example            # copiar a .env (no commitear el .env real)
├── empleados/              # Java Spring Boot (evolución del Reto 1)
│   ├── src/ (entity JPA, JpaRepository, service, controller 201+list,
│   │         client REST departamentos con timeout 2s + 3 reintentos 1s→2s→4s,
│   │         GlobalExceptionHandler {"status","error"}, springdoc)
│   ├── init.sql            # tabla empleados + UNIQUEs
│   ├── Dockerfile
│   └── README.md
└── departamentos/          # Node.js + Express (servicio nuevo)
    ├── src/ (routes, service, pg store + in-memory store para tests, swagger)
    ├── test/ (supertest + node:test, 11 tests)
    ├── init.sql            # tabla departamentos
    ├── Dockerfile
    └── README.md
```

Timeout/reintentos hacia departamentos: timeout 2 s por intento, 3 reintentos con
espera creciente 1 s → 2 s → 4 s. Sin Circuit Breaker todavía (llega en el Reto 3
con el API Gateway, donde tiene sentido).
