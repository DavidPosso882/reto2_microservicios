# ODD — Reto 5: Seguridad y Control de Acceso con JWT

Branch: `reto-5-seguridad-jwt` (base: `reto-4-comunicacion-asincronica`)
Estado base: `b83fe8e` swagger UI vía gateway. `main` atrasado en `a99efb1` (no se usa como base).

## Objetivo
Auth centralizado con JWT, RBAC + propiedad del recurso, ciclo de vida de cuenta por eventos, scheduler de vacaciones.

## Decisiones validadas (2026-09-28)
1. Puerto `auth-service`: **:8086** (vacaciones queda en :8085, gateway :8080 único al host).
2. Validación JWT: **solo en api-gateway** (recomendado PDF, evita 4 lenguajes).
3. Reset token: **Opción A stateless JWT** con `type: RESET_PASSWORD` y expiración corta.
4. Scheduler demo: **como diga el PDF** → fechaInicio=hoy/fechaFin=hoy + scheduler cada minuto configurable por env (+ precisión fecha-hora en dev si hace falta).
5. Catálogo: faltan secciones 3.4-3.7 → extender CATALOGO_EVENTOS.md (pendiente).
6. Seed ADMIN inicial: por env/DB para bootstrap (pendiente definir).

## Tareas y estado
1. [x] Crear branch reto-5 desde reto-4
2. [ ] Validar decisiones 1-5 con usuario
3. [ ] auth-service: login, recover/reset/change-password, hash BCrypt, JWT access + reset, consume 4 eventos / publica 4 eventos, estados ACTIVA|SUSPENDIDA_TEMPORAL|DESACTIVADA_PERMANENTE
4. [ ] Gateway: validación JWT + RBAC + ABAC propiedad (PUT /perfiles/:id propio), 401/403, BearerAuth en OpenAPI
5. [ ] vacaciones-service: scheduler cada minuto (env configurable), publica iniciadas/finalizadas, endpoint dev forzar-inicio solo ADMIN
6. [ ] notificaciones-service: consume 4 eventos auth, logs SEGURIDAD/CUENTA
7. [ ] compose + env: JWT_SECRET vía .env, db-auth, documentar limitación N instancias (ShedLock reto 31)
8. [ ] Verificación e2e 18 pasos del PDF + caso borde retiro en vacaciones + README/diagrama secuencia

## Hallazgos exploración (2026-09-28, scout)
- Gateway `api-gateway/src/app.js`: sin auth, sin jsonwebtoken, proxies por prefijo; interceptar ANTES de /empleados y DESPUÉS de docs; whitelist health+docs+/auth/*; OpenAPI sin BearerAuth.
- Vacaciones Ruby: solo PROGRAMADA/CANCELADA, falta EN_CURSO/FINALIZADA; publisher reutilizable; scheduler nuevo `app/scheduler.rb` con thread en Boot + `SCHEDULER_INTERVAL_S` default 60.
- Notificaciones Python: `consumer.py` ROUTING_KEYS 3 actuales, cola q.notificaciones; agregar 6 keys nuevas en `consumer.py`+`mensajes.py` (SEGURIDAD/CUENTA/VACACIONES).
- Compose: 8085 ocupado por vacaciones → auth en 8086 confirmado; agregar database-auth + vol-auth + JWT_SECRET a gateway y auth.
- Catálogo: faltan 3.4-3.7 + cuenta.activada/desactivada (8 eventos ciclo vida total).
- Riesgo bootstrap: POST /empleados quedaría bloqueado → resolver con POST /auth/bootstrap una sola vez o seed ADMIN.
- Orden sugerido: 1 auth CRUD+JWT → 2 gateway JWT → 3 bootstrap ADMIN → 4 cuenta eventos → 5 scheduler → 6 notif.

## Evidencia
- Branch: `reto-5-seguridad-jwt` creada 2026-09-28 desde `reto-4-comunicacion-asincronica`

## Step 1 — auth-service (2026-09-28, worker)
- auth-service creado: Node 22 + Express 4, puerto 8086, compose con `database-auth` (vol-auth, DB_AUTH_* env) + `JWT_SECRET` requerido también en api-gateway.
- Endpoints: POST /auth/bootstrap (solo tabla vacía), /auth/login, /auth/recover-password, /auth/reset-password (token {sub, type: RESET_PASSWORD} 30min), /auth/change-password (X-User-Id/X-User-Role del gateway o Bearer propio).
- Tokens HS256 con JWT_SECRET (sin default), BCrypt (bcryptjs), política de password (min 8, mayúscula, minúscula, número).
- Estados cuenta: ACTIVA | SUSPENDIDA_TEMPORAL | DESACTIVADA_PERMANENTE; caso borde retiro-durante-vacaciones cubierto por test.
- RabbitMQ: q.auth (4 bindings), ACK manual tras aplicar + dedup eventos_procesados; publica usuario.creado / usuario.recuperacion / cuenta.activada / cuenta.desactivada (envelope catálogo §1).
- Tests: node --test, 32/32 pass (app + rabbit con canal falso). Smoke require('./src/app.js') OK. `docker compose config` OK con JWT_SECRET; sin la var, falla rápido con mensaje claro.
- Fix de tracking descubierto en pruebas: el sombreado this.procesados (Map vs método) se renombró a this.deduplicacion; resta aplicar retiro-durante-SUSPENDIDA en vacaciones.finalizadas (sin evento duplicado) según criterio del task 4.
