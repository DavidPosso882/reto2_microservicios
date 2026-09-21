# ODD — Reto 4: Comunicación Asincrónica y Eventos

Branch: `reto-4-comunicacion-asincronica` (base: `reto-3-api-gateway`)
Decisiones del usuario (2026-09-21): broker **RabbitMQ**, lenguajes nuevos **Python + Go + Ruby**,
vacaciones valida existencia por **réplica local por eventos** (opción b, más trabajo pero autónomo),
catálogo: **contrato propuesto por el agente, a validar antes de implementar**.

## Mapeo servicio ↔ lenguaje (propuesto)

| Servicio | Lenguaje | Puerto interno | Rol mensajería |
|---|---|---|---|
| empleados-service | Java 21 + Spring Boot (existe) | 8081 | Publica 3 eventos |
| departamentos-service | Node.js + Express (existe) | 8082 | Ninguno |
| api-gateway | Node.js + Express (existe) | 8080 (único al host) | Ninguno |
| notificaciones-service | Python (FastAPI o Flask) | 8084 | Consume 3 eventos |
| perfiles-service | Go (stdlib + chi/mux) | 8083 | Consume 3 eventos |
| vacaciones-service | Ruby (Sinatra) | 8085 | Consume 2 + publica 1 |
| message-broker | RabbitMQ 3-management | 5672 / 15672 al host | Infraestructura |

## Tareas y estado

1. [x] Análisis del reto + decisiones (broker, lenguajes, validación-4, catálogo)
2. [ ] Validar `CATALOGO_EVENTOS.md` con el usuario — **bloquea todo lo demás**
3. [ ] Broker en compose + management UI + justificación README
4. [ ] Empleados (Java): PUT + DELETE + filtro estado/rango + publish 3 eventos (TDD: `mvn test`)
5. [ ] Notificaciones (Python): consumer + `eventos_procesados` + GET x2 + OpenAPI + BD propia
6. [ ] Perfiles (Go): consumer + CRUD REST + OpenAPI + BD propia
7. [ ] Vacaciones (Ruby): CRUD + 4 validaciones + réplica empleados + publish + OpenAPI + BD propia
8. [ ] Gateway: rutas /perfiles /notificaciones /vacaciones + `npm test`
9. [ ] README + evidencias (dedup con evento duplicado, flujo e2e, tabla lenguajes)
10. [ ] Verificación e2e completa + `docker compose up --build` limpio

## Hallazgos de exploración (base para el plan)

- `EstadoEmpleado` YA trae `RETIRADO` y `EN_VACACIONES`; falta `fechaRetiro` en la entidad + columna BD (`init.sql`, `ddl-auto=none`).
- Controller NO tiene `PUT /{id}` ni `DELETE /{id}`; service NO tiene actualizar/retirar → crear ambos + tests.
- `GET /empleados` NO acepta query params → agregar `estado`, `desde`, `hasta`.
- Gateway: agregar 3 proxies + envs `PERFILES_URL`, `NOTIFICACIONES_URL`, `VACACIONES_URL` + tests.
- Cada servicio nuevo: Dockerfile + BD Postgres propia (`db-perfiles`, `db-notificaciones`, `db-vacaciones`) + `expose:` sin `ports:`.

## Evidencia / commits

Sin commitear, a decisión del usuario. Todo el trabajo del reto está en el
working tree de `reto-4-comunicacion-asincronica`; no hay hashes de commit
registrados.

- Implementación completa (tareas 2-9): RabbitMQ en compose, eventos Java
  (PUT/DELETE/filtros/publish), notificaciones (Python), perfiles (Go),
  vacaciones (Ruby) con réplica local, rutas de gateway, `CATALOGO_EVENTOS.md`
  y README extendido.
- Tests: empleados `mvn test` 72 · gateway `npm test` 13 · notificaciones
  `pytest` 30 · perfiles `go test ./...` 22 · vacaciones 29.
- Evidencia: `evidencias/reto4/flujo-e2e.log` (run final 18:02Z, 12/12 healthy,
  flujo completo con vacaciones) · `evidencias/reto4/dedup.log` (doble publish
  mismo `id` → 1 perfil / 1 BIENVENIDA / 1 fila de dedup) ·
  `evidencias/reto4/informe-reverification-reto4.md` (defectos D1-D6
  verificados atrás; D5 y D6 resueltos en el run final).
