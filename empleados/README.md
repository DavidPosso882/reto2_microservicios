# Gestión de Empleados - Reto 2

Servidor web REST construido con **Spring Boot 3**, **Java 21**, **Spring Data JPA** y **PostgreSQL** para el registro y consulta de empleados.

Este servicio evoluciona el Reto 1: ahora los empleados se **persisten en PostgreSQL**, el departamento se **valida contra un servicio de departamentos** antes de registrar, se añade el endpoint de **listado** y se expone **Swagger UI**.

---

## Requisitos

| Herramienta | Versión mínima |
|-------------|---------------|
| Java        | 21            |
| Maven       | 3.8+          |
| Docker      | 20+           |
| PostgreSQL  | 14+           |


---

## Base de datos

1. Crea la base de datos:
   ```bash
   createdb gestion_empleados   # o CREATE DATABASE gestion_empleados;
   ```
2. Ejecuta el script `init.sql` para crear la tabla y las restricciones UNIQUE:
   ```bash
   psql -U postgres -d gestion_empleados -f init.sql
   ```

> **Nota sobre unicidad:** el script `init.sql` define restricciones `UNIQUE` a nivel de base de datos sobre `email` y `numero_empleado`. Esa es la **garantía real** contra las carreras de concurrencia: aunque dos peticiones pasen las validaciones de la aplicación casi a la vez, el segundo `INSERT` fallará por violación de unicidad. Las validaciones previas de la aplicación solo sirven para devolver mensajes descriptivos.

El esquema se gestiona con `init.sql` (`spring.jpa.hibernate.ddl-auto=none`); Hibernate no crea la tabla en producción.

---

## Ejecutar localmente (sin Docker)

```bash
# Compilar y ejecutar
mvn spring-boot:run
```

El servidor queda disponible en `http://localhost:8080`.

---

## Ejecutar con Docker

```bash
# 1. Construir la imagen
docker build -t servidor-empleados .

# 2. Ejecutar el contenedor (ajusta las variables de entorno)
docker run -p 8080:8080 \
  -e DB_HOST=host.docker.internal \
  -e DB_PORT=5432 \
  -e DB_NAME=gestion_empleados \
  -e DB_USER=postgres \
  -e DB_PASSWORD=postgres \
  -e DEPARTAMENTOS_URL=http://host.docker.internal:8081 \
  servidor-empleados
```

> La imagen incluye `curl` para health checks y pruebas dentro del contenedor.

---

## Swagger UI

La documentación interactiva (OpenAPI 3) está disponible en:

```
http://localhost:8080/swagger-ui.html
```

Incluye descripciones, códigos de respuesta y esquemas de las operaciones.

---

## Tests

```bash
# Ejecutar la suite de tests (unitarios e integración)
mvn test
```

Los tests usan **H2 en memoria** (sin PostgreSQL) y **stubean la llamada al servicio de departamentos** (sin dependencia viva). La suite incluye:
- Tests unitarios del servicio: `src/test/java/com/empresa/gestionempleados/service/EmpleadoServiceTest.java`
- Tests de integración del controlador con MockMvc: `src/test/java/com/empresa/gestionempleados/controller/EmpleadoControllerIT.java`

---

## Endpoints

### POST /empleados — Registrar un empleado

**Request**
```http
POST http://localhost:8080/empleados
Content-Type: application/json

{
  "id": "E001",
  "nombre": "Juan",
  "apellido": "Pérez",
  "email": "juan.perez@empresa.com",
  "numeroEmpleado": "EMP-2026-001",
  "cargo": "Desarrollador Senior",
  "area": "Tecnología",
  "departamentoId": "IT",
  "fechaIngreso": "2026-02-10",
  "estado": "ACTIVO"
}
```

**Respuesta exitosa — 201 Created** (⚠️ cambió desde el Reto 1, que devolvía 200 OK)
```json
{
  "id": "E001",
  "nombre": "Juan",
  "apellido": "Pérez",
  "email": "juan.perez@empresa.com",
  "numeroEmpleado": "EMP-2026-001",
  "cargo": "Desarrollador Senior",
  "area": "Tecnología",
  "departamentoId": "IT",
  "fechaIngreso": "2026-02-10",
  "estado": "ACTIVO"
}
```

**Respuesta error — 400 Bad Request** (email o numeroEmpleado duplicado)
```json
{
  "status": 400,
  "error": "El email 'juan.perez@empresa.com' ya está registrado"
}
```

**Validación del departamento:** antes de registrar, el servicio llama a
`GET {DEPARTAMENTOS_URL}/departamentos/{departamentoId}` con **timeout de 2 segundos**
y **3 reintentos** con backoff 1s → 2s → 4s.

- Si el departamento no existe (404) → `400` con mensaje:
  ```json
  { "status": 400, "error": "El departamento con id 'IT' no existe" }
  ```
- Si el servicio de departamentos no responde tras agotar los reintentos → `503` y se **rechaza** la operación (nunca se acepta como pendiente):
  ```json
  { "status": 503, "error": "El servicio de departamentos no está disponible en este momento, intente más tarde" }
  ```

**Nota:** el campo `fechaIngreso` debe tener formato `YYYY-MM-DD`; si no, el servidor responde `400 Bad Request`.

---

### GET /empleados — Listar empleados

**Request**
```http
GET http://localhost:8080/empleados
```

**Respuesta — 200 OK** (array JSON, puede estar vacío)
```json
[
  { "id": "E001", "nombre": "Juan", ... },
  { "id": "E002", "nombre": "María", ... }
]
```

---

### GET /empleados/{id} — Consultar un empleado

**Request**
```http
GET http://localhost:8080/empleados/E001
```

**Respuesta exitosa — 200 OK**
```json
{
  "id": "E001",
  "nombre": "Juan",
  "...": "..."
}
```

**Respuesta error — 404 Not Found** (empleado no existe)
```json
{
  "status": 404,
  "error": "El empleado con id E001 no existe"
}
```

---

### Rutas no definidas — 404 Not Found

Cualquier otra ruta o método retorna:
```json
{
  "status": 404,
  "error": "Recurso no encontrado"
}
```

---

## Pruebas con curl

```bash
# Registrar un empleado (espera 201 Created)
curl -X POST http://localhost:8080/empleados \
  -H "Content-Type: application/json" \
  -d '{
    "id": "E001",
    "nombre": "Juan",
    "apellido": "Pérez",
    "email": "juan.perez@empresa.com",
    "numeroEmpleado": "EMP-2026-001",
    "cargo": "Desarrollador Senior",
    "area": "Tecnología",
    "departamentoId": "IT",
    "fechaIngreso": "2026-02-10"
  }'

# Listar empleados
curl http://localhost:8080/empleados

# Consultar un empleado
curl http://localhost:8080/empleados/E001

# Empleado no existe (espera 404)
curl http://localhost:8080/empleados/E999

# Ruta no definida (espera 404)
curl http://localhost:8080/otra-ruta

# Swagger UI
open http://localhost:8080/swagger-ui.html
```

---

## Modelo canónico del empleado

| Campo            | Tipo   | Descripción                                      |
|------------------|--------|--------------------------------------------------|
| `id`             | String | Identificador único del empleado (clave primaria)|
| `nombre`         | String | Nombre del empleado                              |
| `apellido`       | String | Apellido del empleado                            |
| `email`          | String | Email único (UNIQUE en BD)                       |
| `numeroEmpleado` | String | Número de empleado único (UNIQUE en BD)          |
| `cargo`          | String | Cargo o puesto                                   |
| `area`           | String | Área de trabajo                                  |
| `departamentoId` | String | ID del departamento validado contra el servicio  |
| `fechaIngreso`   | String | Fecha de ingreso (formato YYYY-MM-DD)            |
| `estado`         | Enum   | `ACTIVO` / `EN_VACACIONES` / `RETIRADO`          |

> En el Reto 2 el estado siempre es `ACTIVO` y se persiste como String (`EnumType.STRING`). Las transiciones de estado se implementan en retos posteriores.

---

## Estructura del proyecto

```
gestion-empleados/
├── init.sql
├── Dockerfile
├── pom.xml
├── README.md
└── src/
    ├── main/
    │   ├── java/com/empresa/gestionempleados/
    │   │   ├── GestionEmpleadosApplication.java
    │   │   ├── client/
    │   │   │   ├── DepartamentoClient.java
    │   │   │   └── DepartamentoRestClient.java
    │   │   ├── config/
    │   │   │   └── OpenApiConfig.java
    │   │   ├── controller/
    │   │   │   └── EmpleadoController.java
    │   │   ├── exception/
    │   │   │   ├── DepartamentoNoDisponibleException.java
    │   │   │   ├── DepartamentoNoExisteException.java
    │   │   │   ├── EmpleadoDuplicadoException.java
    │   │   │   ├── EmpleadoNotFoundException.java
    │   │   │   ├── ErrorResponse.java
    │   │   │   └── GlobalExceptionHandler.java
    │   │   ├── model/
    │   │   │   ├── Empleado.java
    │   │   │   └── EstadoEmpleado.java
    │   │   ├── repository/
    │   │   │   └── EmpleadoRepository.java
    │   │   └── service/
    │   │       └── EmpleadoService.java
    │   └── resources/
    │       └── application.properties
    └── test/
        ├── java/com/empresa/gestionempleados/
        │   ├── controller/
        │   │   └── EmpleadoControllerIT.java
        │   └── service/
        │       └── EmpleadoServiceTest.java
        └── resources/
            └── application.properties
```
