# Proyecto Final — Sistema de Gestión de Empleados (Microservicios)

Automatización del ciclo de vida del empleado (onboarding, perfil, vacaciones,
retiro) con arquitectura event-driven: 6 microservicios de negocio + API
Gateway como único borde, mensajería RabbitMQ, observabilidad completa
(Prometheus/Grafana/Loki/Zipkin) y CI por servicio en Jenkins. Detalle de
decisiones en `docs/arquitectura.md`, eventos en `docs/eventos.md`.

## 1. Requisitos previos

- Docker + Docker Compose (v2) y 8 GB libres (22 contenedores).
- Puertos libres en el host: `8080` (gateway), `9090` (Jenkins), `3000`
  (Grafana), `9091` (Prometheus), `9411` (Zipkin), `3100` (Loki),
  `15672` (RabbitMQ UI), `5000` (registry), `9000` (SonarQube).

## 2. Ejecución

```bash
cd proyecto-final-microservicios

# Configuración local (una sola vez; genera JWT y secretos fuera de git)
cp .env.example .env
bash scripts/setup-secrets.sh

# Levantar todo el sistema
docker compose up --build

# Accesos
# - API Gateway:      http://localhost:8080
# - Gateway agregado: http://localhost:8080/empleados/E001/completo
# - RabbitMQ UI:      http://localhost:15672
# - Jenkins:          http://localhost:9090
# - SonarQube:        http://localhost:9000
# - Grafana:          http://localhost:3000
# - Prometheus:       http://localhost:9091
# - Trazas (Zipkin):  http://localhost:9411
# - Registry:         http://localhost:5000
```

Primer ADMIN y pruebas E2E:

```bash
BASE_URL=http://localhost:8080 python3 scripts/wait-for-e2e-ready.py
cd e2e-tests && ./run_bdd.sh   # 18 escenarios, ~1 min
```

CI: Jenkins + SonarQube + registry salen con el compose; los pipelines por
servicio requieren `git init` local una vez (ver
docs/guias/ci-jenkins-sonar.md § Primer arranque).

## 3. Tecnologías

| Microservicio | Lenguaje | Puerto interno | BD |
|---|---|---|---|
| api-gateway | Node.js 22 + Express | 8080 (único al host) | — |
| autenticacion | Node.js 22 + Express | 8086 | PostgreSQL |
| gestion-empleados | Java 21 + Spring Boot | 8081 | PostgreSQL |
| gestion-departamentos | Node.js 22 + Express | 8082 | PostgreSQL |
| gestion-perfiles | Go 1.26 | 8083 | PostgreSQL |
| gestion-vacaciones | Ruby 3.3 + Sinatra | 8085 | PostgreSQL |
| notificaciones | Python 3.12 + FastAPI | 8084 | PostgreSQL |

5 lenguajes. Broker: RabbitMQ (`ecosistema.eventos`, topic). Observabilidad:
Prometheus + Grafana + Loki/Promtail + Zipkin (OpenTelemetry, W3C).
CI: Jenkins + SonarQube + registry local. Scale/resiliencia: stateless +
Circuit Breaker empleados→departamentos (`GET /empleados/circuit/state`).

## 4. Endpoints principales (vía `http://localhost:8080`)

| Método | Ruta | Auth |
|---|---|---|
| POST | `/auth/bootstrap` (solo tabla vacía), `/auth/login`, `/auth/recover-password`, `/auth/reset-password` | no |
| POST | `/auth/change-password` | sí |
| GET/POST | `/empleados`, GET `/empleados?estado=RETIRADO&desde=&hasta=` (auditoría) | sí |
| GET/PUT/DELETE | `/empleados/{id}` (DELETE = retiro, no borra) | sí (ADMIN escribe) |
| GET | `/empleados/{id}/completo` (empleado+perfil; degradado si perfiles cae) | sí |
| GET/POST | `/departamentos` | sí |
| GET/PUT | `/perfiles/{empleadoId}` (PUT solo el propio, 403 ajeno) | sí |
| GET/POST | `/vacaciones` | sí |
| GET | `/health`, `/metrics`, docs (`/empleados/swagger-ui.html`, `/notificaciones/docs`, `/perfiles/docs`, `/vacaciones/docs`, `/auth/...` vía gateway) | no/sí |

```bash
TOKEN=$(curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@empresa.com","password":"Admin123!"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['accessToken'])")
curl http://localhost:8080/empleados -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8080/departamentos -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"id":"TEC","nombre":"Tecnología"}'
```

Flujos: onboarding crea la cuenta inactiva + envía token por correo (la
contraseña solo la pone el empleado, hasheada BCrypt); vacaciones
desactivan/reactivan por scheduler con notificación; el retiro desactiva
permanente (el reset no lo revierte) y queda en auditoría.

## 5. Configuración inicial y secretos

```bash
cp .env.example .env          # las 26 variables con placeholders
bash scripts/setup-secrets.sh # genera JWT_SECRET (64 hex) + secrets/jwt_secret.txt
python3 scripts/grafana-set-telegram.py  # conecta el bot (ver docs/guias/telegram-bot.md)
```

`.env` y `secrets/` están ignorados por git: el repo es publicable sin
filtrar credenciales. Rotación: regenerar con el script y recrear
contenedores (el JWT invalida todos los tokens emitidos).

## 6. Accesos por defecto (sin contraseñas reales en este documento)

- **ADMIN semilla**: se crea con `POST /auth/bootstrap` una sola vez
  (email/password a elección); `wait-for-e2e-ready.py` usa `ADMIN_EMAIL` /
  `ADMIN_PASSWORD` (default `admin@empresa.com`, ver script).
- **Grafana**: `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` del `.env`.
- **RabbitMQ UI**: `RABBITMQ_USER` / `RABBITMQ_PASSWORD` del `.env`.
- **SonarQube/Jenkins**: credenciales `sonar-token` y `jwt-secret` provistas
  por entorno (`SONAR_TOKEN`, `JWT_SECRET`); ver `docs/guias/ci-jenkins-sonar.md`.
- **Bases de datos**: `DB_*_USER` / `DB_*_PASSWORD` del `.env` (solo red Docker).
