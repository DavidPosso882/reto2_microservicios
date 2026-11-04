# Arquitectura del Sistema

## Diagrama

```mermaid
flowchart TB
    C[Cliente Browser/App] -->|REST HTTPS| GW[API Gateway :8080<br/>único borde + JWT + /completo]
    GW -->|REST| AUTH[Autenticación :8086<br/>Node 22]
    GW -->|REST| EMP[Empleados :8081<br/>Java 21]
    GW -->|REST| DEP[Departamentos :8082<br/>Node 22]
    GW -->|REST| PER[Perfiles :8083<br/>Go 1.26]
    GW -->|REST| VAC[Vacaciones :8085<br/>Ruby 3.3 + scheduler]
    GW -->|REST| NOT[Notificaciones :8084<br/>Python 3.12]
    EMP -->|REST + Circuit Breaker<br/>timeout 2s, reintentos, fallback| DEP
    EMP -.->|empleado.creado/actualizado/retirado| BK[(RabbitMQ<br/>ecosistema.eventos)]
    VAC -.->|vacaciones.programadas/iniciadas/finalizadas| BK
    AUTH -.->|usuario.creado/recuperacion<br/>cuenta.activada/desactivada| BK
    BK -.-> AUTH & PER & NOT & VAC
    EMP --- DB1[(PG empleados)]
    AUTH --- DB2[(PG auth)]
    DEP --- DB6[(PG departamentos)]
    PER --- DB3[(PG perfiles)]
    VAC --- DB4[(PG vacaciones)]
    NOT --- DB5[(PG notificaciones)]
    GW & AUTH & EMP & DEP & PER & VAC & NOT -->|/metrics + OTel + logs JSON| OBS[Prometheus :9091<br/>Grafana :3000 · Loki :3100<br/>Zipkin :9411]
    OBS -->|alertas| TG[Telegram]
    JX[Jenkins :9090<br/>SonarQube :9000<br/>Registry :5000] -.->|CI por servicio| GW & AUTH & EMP & DEP & PER & VAC & NOT
```

Red única `microservices-network` (decisión: segmentación por capas del diagrama
de referencia no aporta aislamiento real sin políticas; un solo compose
despliega todo con `docker compose up --build`).

## Decisiones

- **Borde único**: solo el gateway publica puerto HTTP (:8080). Auth en :8086,
  resto 8081–8085 internos (`expose`). Sin `/register` público: las cuentas
  nacen del evento `empleado.creado`, inactivas y sin contraseña (BCrypt solo al
  establecerla el empleado con token de 30 min).
- **Auth opción (a)**: JWT propio HS256 con secreto compartido gateway+auth
  (fail-fast si falta). Sin IdP externo.
- **Resiliencia**: empleados→departamentos con timeout (2s), reintentos con
  backoff y Circuit Breaker con fallback (`PENDIENTE_VALIDACION`) + endpoint
  observable `GET /empleados/circuit/state`. Servicios stateless; el scheduler
  de vacaciones es de instancia única documentada.
- **Agregado opcional**: `GET /empleados/:id/completo` (gateway, con código)
  combina empleado+perfil; si perfiles cae responde 200 degradado
  (`perfil: null, degradado: true`) con timeout de 2.5s. Los gateways
  declarativos no componen: por eso el gateway es Express con código propio.
- **Eventos**: envelope común + deduplicación obligatoria por `id` + W3C por
  cabeceras AMQP (ver `docs/eventos.md`). Traza de onboarding verificada:
  51 spans, 7 servicios, un `traceId`.
- **Observabilidad**: Prometheus (scrape 15s, 7 jobs) + Grafana aprovisionado
  (datasources, dashboard ecosistema, 2 reglas, contact point Telegram) +
  Loki/Promtail (logs JSON con `traceId`) + Zipkin. Límite hallado: Grafana
  rechaza `chat_id` numérico por `$VAR` (infiere número); el repo trae template
  y `scripts/grafana-set-telegram.py` genera el fichero con valores citados.
- **Salud**: `GET /health` → `{"status":"UP|DOWN","service":"...","checks":
  {"database":"UP|DOWN","messageBroker":"UP|DOWN"}}` (200/503). Gateway y
  departamentos reportan `N/A` donde no tienen dependencia propia (sin broker
  cliente): honesto y documentado; su `DOWN` lo gobierna lo que sí usan.
- **Cobertura**: mínimo 70% con gate en pipeline (nativo donde se puede,
  Quality Gate SonarQube en todos). Perfiles mide alcance unitario
  (fuera `cmd/` y `store/postgres/`, que exigen runtime vivo y los cubre el
  BDD contra el stack desplegado).
- **Docker**: multistage donde hay compilación (Java, Go, Ruby); Node/Python
  single-stage optimizado (`--omit=dev`, cache de capas, `.dockerignore`).
- **Secretos**: cero en git (`.env` + `secrets/` ignorados, `.env.example` con
  las 26 variables, `scripts/setup-secrets.sh` genera JWT). Rotación: regenerar
  con el script y recrear contenedores; el JWT invalida todos los tokens.
- **CI**: un `Jenkinsfile` por servicio (Checkout/Build/Test/SonarQube con
  `qualitygate.wait`/Package al registry/E2E); tests rojos → UNSTABLE o
  FAILURE, cobertura <70% o QG rojo → FAILURE.
