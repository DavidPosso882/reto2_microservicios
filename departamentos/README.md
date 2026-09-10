# Gestión de Departamentos - Reto 2

Microservicio REST para la gestión de departamentos, construido con **Node.js + Express** y **PostgreSQL** (`pg`). Complementa al servicio de empleados del Reto 1 y se integra en la orquestación con Docker Compose del Reto 2.

---

## Requisitos

| Herramienta | Versión mínima |
|-------------|---------------|
| Node.js     | 18+           |
| PostgreSQL  | 12+           |
| Docker      | 20+           |

---

## Variables de entorno

Configuración vía variables de entorno. Copie `.env.example` a `.env` y ajuste los valores.

| Variable      | Descripción                          | Valor por defecto |
|---------------|--------------------------------------|-------------------|
| `PORT`        | Puerto del servidor HTTP             | `8081`            |
| `DB_HOST`     | Host de la base de datos PostgreSQL  | `localhost`       |
| `DB_PORT`     | Puerto de PostgreSQL                 | `5432`            |
| `DB_NAME`     | Nombre de la base de datos           | `departamentos`   |
| `DB_USER`     | Usuario de PostgreSQL                | `postgres`        |
| `DB_PASSWORD` | Contraseña de PostgreSQL             | `postgres`        |

---

## Base de datos

Cree la base de datos y aplique el esquema:

```bash
psql -h localhost -U postgres -c "CREATE DATABASE departamentos;"
psql -h localhost -U postgres -d departamentos -f init.sql
```

`init.sql` crea la tabla `departamentos` con `id` (clave primaria), `nombre` y `descripcion` (ambos NOT NULL) usando `CREATE TABLE IF NOT EXISTS`, por lo que es seguro ejecutarlo varias veces.

---

## Ejecutar localmente (sin Docker)

```bash
npm install
npm start
```

El servidor queda disponible en `http://localhost:8081`.

---

## Ejecutar con Docker

```bash
docker build -t servidor-departamentos .
docker run -p 8081:8081 --env-file .env servidor-departamentos
```

El servidor queda disponible en `http://localhost:8081`.

> El `Dockerfile` incluye `curl` (imagen `node:22-alpine`) para que el health check del Compose pueda apuntar a `GET /departamentos`.

---

## Tests

```bash
npm test
```

La suite usa `node:test` + `supertest`:

- `test/departamento.test.js` — pruebas de rutas y validación con un almacén en memoria inyectable (no requiere base de datos).
- `test/integration/departamento.pg.integration.test.js` — prueba de integración contra PostgreSQL real. Se omite (`skip`) automáticamente si la base de datos no está disponible.

---

## Endpoints

### POST /departamentos — Registrar un departamento

```http
POST http://localhost:8081/departamentos
Content-Type: application/json

{
  "id": "IT",
  "nombre": "Tecnología",
  "descripcion": "Área de tecnología de la información"
}
```

**Respuesta exitosa — 201 Created**

```json
{
  "id": "IT",
  "nombre": "Tecnología",
  "descripcion": "Área de tecnología de la información"
}
```

**Respuesta error — 400 Bad Request** (campos faltantes o id duplicado)

```json
{
  "status": 400,
  "error": "El departamento con id IT ya existe"
}
```

### GET /departamentos/{id} — Consultar un departamento

```http
GET http://localhost:8081/departamentos/IT
```

**Respuesta exitosa — 200 OK**

```json
{
  "id": "IT",
  "nombre": "Tecnología",
  "descripcion": "Área de tecnología de la información"
}
```

**Respuesta error — 404 Not Found**

```json
{
  "status": 404,
  "error": "El departamento con id IT no existe"
}
```

### GET /departamentos — Listar todos los departamentos

```http
GET http://localhost:8081/departamentos
```

**Respuesta exitosa — 200 OK** (arreglo JSON; vacío si no hay registros)

```json
[
  {
    "id": "IT",
    "nombre": "Tecnología",
    "descripcion": "Área de tecnología de la información"
  }
]
```

---

## Documentación OpenAPI (Swagger)

La documentación interactiva se sirve con **Swagger UI** en:

```
http://localhost:8081/api-docs
```

Documenta los tres endpoints con sus códigos de respuesta (`200`, `201`, `400`, `404`, `500`) y los esquemas `Departamento` y `ErrorEnvelope`.

---

## Pruebas con curl

```bash
# Registrar un departamento
curl -X POST http://localhost:8081/departamentos \
  -H "Content-Type: application/json" \
  -d '{"id":"IT","nombre":"Tecnología","descripcion":"Área de TI"}'

# Consultar un departamento
curl http://localhost:8081/departamentos/IT

# Departamento no existe (espera 404)
curl http://localhost:8081/departamentos/NOPE

# Listar todos
curl http://localhost:8081/departamentos
```

---

## Estructura del proyecto

```
departamentos/
├── init.sql
├── Dockerfile
├── .dockerignore
├── .env.example
├── package.json
├── README.md
└── src/
    ├── server.js                 # Punto de entrada
    ├── app.js                    # Fábrica de la aplicación Express
    ├── errors.js                 # Errores con estado HTTP y mensaje en español
    ├── swagger.js                # Configuración de OpenAPI (Swagger)
    ├── config/
    │   └── db.js                 # Pool de conexiones pg desde variables de entorno
    ├── routes/
    │   └── departamentoRoutes.js # Endpoints /departamentos
    ├── service/
    │   └── DepartamentoService.js# Validación y lógica de negocio
    └── store/
        ├── PgDepartamentoStore.js        # Persistencia con PostgreSQL
        └── InMemoryDepartamentoStore.js  # Almacén en memoria para tests
```