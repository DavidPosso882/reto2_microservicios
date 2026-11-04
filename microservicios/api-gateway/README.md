# api-gateway (Reto 3)

Punto de entrada único al ecosistema. Reverse proxy de aplicación (Node.js +
Express + http-proxy-middleware): enruta por prefijo de ruta y no contiene
lógica de negocio.

## Enrutamiento

| Ruta externa | Destino interno |
|---|---|
| `/empleados`, `/empleados/*` | `empleados-service` (`EMPLEADOS_URL`) |
| `/departamentos`, `/departamentos/*` | `departamentos-service` (`DEPARTAMENTOS_URL`) |
| `/health` | Propio: `{"status":"ok","service":"api-gateway"}` |

Cuerpo, cabeceras, query strings y códigos de estado viajan intactos. Si el
destino no responde: `503 {"status":503,"error":"..."}` (nunca una página del
framework). Rutas desconocidas: `404 {"status":404,"error":"Recurso no encontrado"}`.

## Variables de entorno

| Variable | Defecto en Compose |
|---|---|
| `PORT` | `8080` (único puerto publicado al host) |
| `EMPLEADOS_URL` | `http://empleados-service:8080` |
| `DEPARTAMENTOS_URL` | `http://departamentos-service:8081` |

## Tests

```bash
npm test   # node:test + fakes locales, sin Docker: 7 tests
```
