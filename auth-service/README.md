# auth-service (Reto 5): identidad, JWT y ciclo de vida de cuentas

Servicio de identidad del ecosistema: firma y verifica JWT de acceso (HMAC
SHA-256), gestiona el establecimiento/recuperación de contraseñas con tokens
reset stateless y conduce el ciclo de vida de las cuentas (`ACTIVA |
SUSPENDIDA_TEMPORAL | DESACTIVADA_PERMANENTE`) consumiendo y publicando los
eventos del catálogo (`CATALOGO_EVENTOS.md`).

- **Stack:** Node.js 22 + Express 4 (mismo stack del gateway/departamentos,
  comparte la librería `jsonwebtoken` con la validación del gateway).
- **Puerto interno:** `:8086` (sin binding al host; el único borde sigue siendo
  el gateway en `:8080`).
- **Base de datos:** PostgreSQL dedicada `database-auth` (db `auth_db`),
  tabla `usuarios` + cacheo de eventos `eventos_procesados`.
- **Tokens:** access JWT `{ sub, role: ADMIN|USER, iat, exp }` HS256 y reset
  token `{ sub, type: RESET_PASSWORD, iat, exp }` con expiración corta.
  Ambos firmados con `JWT_SECRET`. La contraseña **nunca** viaja en el token;
  se almacena hasheada con **BCrypt**.

## Correr local (sin Docker)

```bash
npm install
DB_HOST=localhost DB_NAME=auth_db JWT_SECRET=dev-secret npm start
```

## Cómo obtener un token (flujo completo)

1. **Seed del ADMIN** (solo con la tabla `usuarios` vacía, destraba el
   `POST /empleados` protegido):

   ```bash
   curl -X POST http://localhost:8080/auth/bootstrap \
     -H 'Content-Type: application/json' \
     -d '{"email":"admin@empresa.com","password":"AdminClave1"}'
   # → 201 { id: "ADMIN", email: "admin@empresa.com", role: "ADMIN", estado: "ACTIVA" } (el password nunca se devuelve)
   ```

2. **Login USER** (tras activar la cuenta; ver paso 3):

   ```bash
   curl -X POST http://localhost:8080/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"e001@empresa.com","password":"ClaveNueva1"}'
   # → 200 { accessToken, tokenType: "Bearer", expiresIn, usuario }
   ```

3. **Activación / recuperación de un usuario (reset token):**
   `POST /empleados` publica `empleado.creado`, el auth-service crea la cuenta
   inactiva y publica `usuario.creado` con un `resetToken` que aparece en los
   logs de `notificaciones-service` (canal de email simulado). Con ese token:

   ```bash
   curl -X POST http://localhost:8080/auth/reset-password \
     -H 'Content-Type: application/json' \
     -d '{"token":"<resetToken>","nuevaPassword":"ClaveNueva1"}'
   # activa la cuenta y publica cuenta.activada (motivo ESTABLECIMIENTO_PASSWORD)
   ```

   `POST /auth/recover-password` funciona igual (publica `usuario.recuperacion`
   con un reset token nuevo, expira en 30 min).

4. **Cambio de contraseña autenticado** (JWT u otra identidad válida):

   ```bash
   curl -X POST http://localhost:8080/auth/change-password \
     -H "Authorization: Bearer <accessToken>" \
     -H 'Content-Type: application/json' \
     -d '{"passwordActual":"...","passwordNueva":"..."}'
   ```

Política de contraseñas documentada: mínimo 8 caracteres, mayúscula,
minúscula y número (`src/passwordPolicy.js`).

## Ciclo de vida de cuentas (eventos)

| Evento consumido | Efecto | Evento publicado |
|---|---|---|
| `empleado.creado` | crea cuenta USER sin contraseña (suspendida) | `usuario.creado` (con reset token) |
| `empleado.retirado` | baja permanente | `cuenta.desactivada` (RETIRO, permanente=true) |
| `vacaciones.iniciadas` | suspensión temporal | `cuenta.desactivada` (VACACIONES, permanente=false) |
| `vacaciones.finalizadas` | reactiva SOLO si no hay baja permanente | `cuenta.activada` (FIN_VACACIONES) |

Transporte: exchange topic `ecosistema.eventos`, cola propia `q.auth` con
ACK manual después de persistir el efecto + el `id` del envelope en
`eventos_procesados` (deduplicación idempotente). El caso borde del PDF
(**retiro durante vacaciones**) se resuelve con el estado
`DESACTIVADA_PERMANENTE`: `vacaciones.finalizadas` no reactiva cuentas con
baja permanente (test con assertion explícita en
`test/auth.routes.test.js`).

## Seguridad notas

- `JWT_SECRET` obligatorio vía env (`docker-compose.yml` también lo inyecta al
  gateway para la validación de la tarea 2). Sin defaults: el servicio no
  arranca con un secreto débil implícito.
- TTLs configurables: `JWT_ACCESS_TTL_MINUTES` (60 default) y
  `JWT_RESET_TTL_MINUTES` (30 default; el PDF permite 15-60).
- Los tokens de reset llevan el claim `type: RESET_PASSWORD`; un access token
  no puede usarse como reset ni viceversa (verificado en tests).
- Login/recover responden 401/200 de manera uniforme (no filtran si el email
  existe).
- BCrypt rounds configurables (`BCRYPT_ROUNDS`, default 10).

## Limitación conocida

La entrega RabbitMQ a una sola instancia es suficiente para este reto; un
escenario multi-instancia de auth-service requeriría coordinar el consumo
(ShedLock/Reto 31) — por ahora, una única réplica es la configuración soportada.
