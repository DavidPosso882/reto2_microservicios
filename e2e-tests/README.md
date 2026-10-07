# e2e-tests — Pruebas E2E BDD (Reto 6)

Proyecto **independiente** del stack (no toca compose, `.env` ni servicios):
pruebas de extremo a extremo en Python con **Behave** (Gherkin en español) y
**requests**, apuntando al **gateway** en `http://localhost:8080`.

Estado P2+P3: humo verde (1 escenario) y seguridad RBAC verde (4 escenarios).
El polling de eventos asíncronos de negocio queda para P4 (ver
`features/support/polling.py`); el Punto 3 solo usa una espera acotada en la
preparación del token USER. Los escenarios RBAC son síncronos (sin polling).

## Estructura

```text
e2e-tests/
├── behave.ini                  # formatter JSON + junit + pretty a stdout
├── requirements.txt            # behave, requests (versiones fijadas)
├── features/
│   ├── environment.py          # hooks: contexto limpio + run_id único por escenario
│   ├── humo.feature            # escenario de humo (# language: es)
│   ├── seguridad.feature       # RBAC: 401 sin token, 403 USER, ADMIN 200/201/200
│   ├── steps/
│   │   ├── common_steps.py     # sistema operativo / código de respuesta
│   │   ├── auth_steps.py       # login (Background) + activación de cuenta USER real
│   │   └── seguridad_steps.py  # pasos RBAC del Punto 3
│   └── support/
│       ├── config.py           # BASE_URL, credenciales por entorno y depto E2E
│       ├── api_client.py       # requests.Session + Bearer + GET/POST/PUT/DELETE
│       └── polling.py          # stub documentado (se implementa en P4)
└── reports/                    # generado por behave (gitignored)
```

## Requisitos y ejecución

Python 3.11+ y el venv local (el stack debe estar levantado aparte):

```bash
cd e2e-tests
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# un solo comando (con el venv activado también funciona `behave` a secas)
.venv/bin/behave

# solo el feature de seguridad RBAC (requiere ADMIN_* en el entorno)
.venv/bin/behave features/seguridad.feature
```

`behave` sin flags muestra el resultado (`pretty`) en consola y deja los
reportes en `reports/`; no hace falta pasar `-f json -o ... --junit ...`
porque ya está configurado en `behave.ini` (equivale a
`behave -f json -o reports/cucumber.json --junit --junit-directory reports`,
añadiendo `pretty` a stdout).

## Variables de entorno

Ningún secreto se versiona: credenciales y URL se inyectan por entorno.

| Variable | Default | Uso |
|---|---|---|
| `BASE_URL` | `http://localhost:8080` | URL del gateway |
| `SMOKE_PATH` | `/health` | Endpoint público del humo |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | (sin default) | Login `"admin"` en Antecedentes |
| `USER_EMAIL` / `USER_PASSWORD` | (sin default) | Login `"user"` en Antecedentes (cuentas ya existentes) |
| `E2E_USER_PASSWORD` | `User1234` | Password de la cuenta USER sintética que activa el P3 (no es secreto) |
| `HTTP_TIMEOUT` | `10` | Timeout HTTP en segundos |

Ejemplo local (el escenario de humo no necesita credenciales; seguridad sí):

```bash
cd e2e-tests
ADMIN_EMAIL=admin@empresa.com ADMIN_PASSWORD=... .venv/bin/behave
```

Si un feature usa el Background de login y falta la variable, el escenario
falla indicando exactamente qué `*_EMAIL` / `*_PASSWORD` definir.

## Humo: endpoint elegido

Sondeo contra `http://localhost:8080` (P2, stack 14/14 healthy):

| Endpoint | Código | Nota |
|---|---|---|
| `GET /health` | **200** | **elegido** — `{"status":"ok","service":"api-gateway"}`, sin token y sin depender de otro servicio |
| `GET /api-docs` | 401 | requiere JWT |
| `GET /docs` | 401 | requiere JWT |
| `GET /notificaciones/docs` | 200 | depende de notificaciones-service |
| `GET /auth/docs` | 401 | requiere JWT |
| `GET /empleados` | 401 | prueba de vida del gateway si no hubiera ningún 200 |

Se prefiere un 200 real del propio gateway: si no existiera, el humo habría
aceptado `GET /empleados` → 401 como "gateway vivo" (documentando el motivo),
pero `/health` ya es público y estable.

## Reportes

Cada corrida genera:

* `reports/cucumber.json` — formatter JSON (estilo cucumber), con todos los
  features ejecutados.
* `reports/TESTS-<feature>.xml` — JUnit XML por feature
  (`TESTS-humo.xml`, `TESTS-seguridad.xml`).
* consola — formatter `pretty`.

`reports/` está gitignored: los reportes no se commitean. El reporte HTML
completo queda para P6.

## Autenticación en Antecedentes (Background)

El gateway exige JWT (Reto 5). Para no repetir el login en cada escenario, un
feature protegido declara:

```gherkin
# language: es

Característica: Consulta protegida
  Antecedentes:
    Dado que inicio sesión como "admin"

  Escenario: Consultar empleados
    ...
```

`auth_steps.py` hace `POST /auth/login` vía gateway con `ADMIN_EMAIL` /
`ADMIN_PASSWORD` (o `USER_*` si el rol es `"user"`), guarda el token en
`context.token` y `context.tokens[rol]`, y lo aplica como
`Authorization: Bearer` en la sesión del escenario. `before_scenario` crea
una instancia nueva por escenario: sin token ni respuesta heredados.

## Seguridad RBAC (Punto 3)

`features/seguridad.feature` verifica el control de acceso del gateway con 4
escenarios independientes, todos con `Antecedentes` (login ADMIN +
departamento E2E asegurado de forma idempotente):

| Escenario | Qué verifica |
|---|---|
| Acceso denegado sin token | `GET /empleados` sin Bearer -> 401 (escenario base del PDF) |
| Token inválido o malformado | Bearer con firma inválida y Bearer sin forma JWT -> 401 |
| USER puede consultar pero no escribir | `GET /empleados` -> 200; `POST` y `DELETE` -> 403 |
| ADMIN puede consultar, registrar y retirar | `GET` -> 200; `POST` -> 201; `DELETE` -> 200 |

Códigos observados contra el stack levantado (no inventados):

| Caso | Endpoint | Código |
|---|---|---|
| Sin token | `GET /empleados` | 401 |
| Token inválido (firma) o malformado | `GET /empleados` | 401 |
| USER (token válido) | `GET /empleados` | 200 |
| USER (token válido) | `POST /empleados` | 403 |
| USER (token válido) | `DELETE /empleados/{id}` | 403 |
| ADMIN | `GET /empleados` | 200 |
| ADMIN | `POST /empleados` | 201 |
| ADMIN | `DELETE /empleados/{id}` | 200 |

El corte es responsabilidad del gateway (`api-gateway/src/middleware/auth.js`):
`authenticate` responde 401 cuando no puede probar identidad (token ausente,
válido mal firmado/vencido o malformado); `authorizeService` responde 403
cuando la identidad es válida pero el rol no alcanza. Por diseño nunca hay 401
por falta de permisos con un token válido.

### Cómo se obtiene el token USER (sin usuarios prefabricados)

No hay cuentas USER semilla. El paso `Dado que tengo un token de usuario
activo` reproduce el flujo real del Reto 5:

1. ADMIN registra un empleado único `E2E-P3-USER-<run_id>` (`POST /empleados`
   -> 201).
2. El evento `empleado.creado` crea la cuenta USER `SUSPENDIDA_TEMPORAL` en
   auth-service (asíncrono por RabbitMQ).
3. Se espera (polling acotado de hasta 30 s) la notificación de
   `usuario.creado` en `GET /notificaciones/{id}` y se extrae de su mensaje el
   token de activación.
4. `POST /auth/reset-password` activa la cuenta con `E2E_USER_PASSWORD`
   (default `User1234`, no es un secreto real).
5. `POST /auth/login` devuelve el access token USER real, que se usa como
   Bearer en el resto del escenario.

IDs únicos: `before_scenario` genera `context.run_id` (uuid4) y todos los
datos llevan el sufijo (`E2E-P3-<run_id>`, `E2E-P3-USER-<run_id>`,
`e2e-p3-*-<run_id>@empresa.com`), así que dos corridas o dos escenarios
nunca chocan. El departamento compartido `E2E-P3-DEPT` se crea una sola vez
(la primera corrida) y luego se reutiliza.

## Polling

No se implementa como helper de negocio en P2/P3. `support/polling.py` queda
como stub documentado que falla explícitamente si se usa; el helper real
(`wait_until(...)` con timeout e intervalo) llega en P4 junto con los flujos
asíncronos. El Punto 3 solo usa una espera acotada dentro del paso de
preparación del token USER (creación de cuenta por RabbitMQ); los escenarios
RBAC en sí son síncronos.
