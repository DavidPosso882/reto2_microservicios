# e2e-tests — Pruebas E2E BDD (Reto 6)

Proyecto **independiente** del stack (no toca compose, `.env` ni servicios):
pruebas de extremo a extremo en Python con **Behave** (Gherkin en español) y
**requests**, apuntando al **gateway** en `http://localhost:8080`.

Estado P2+P3+P4: humo verde (1 escenario), seguridad RBAC verde (4) y
onboarding asíncrono verde (5). El polling real vive en
`features/support/polling.py` y lo comparten la activación USER del P3 y los
escenarios `eventualmente` del P4; los escenarios RBAC siguen siendo
síncronos (sin polling).

## Estructura

```text
e2e-tests/
├── behave.ini                  # formatter JSON + junit + pretty a stdout
├── requirements.txt            # behave, requests (versiones fijadas)
├── features/
│   ├── environment.py          # hooks: contexto limpio + run_id único por escenario
│   ├── humo.feature            # escenario de humo (# language: es)
│   ├── seguridad.feature       # RBAC: 401 sin token, 403 USER, ADMIN 200/201/200
│   ├── onboarding.feature      # P4: alta -> auth + notificación + reset/login, 5 escenarios
│   ├── steps/
│   │   ├── common_steps.py     # sistema operativo / código de respuesta
│   │   ├── auth_steps.py       # login (Background) + activación de cuenta USER real
│   │   ├── seguridad_steps.py  # pasos RBAC del Punto 3 (login/depto reutilizados)
│   │   └── onboarding_steps.py # pasos asíncronos del Punto 4 (eventualmente)
│   └── support/
│       ├── config.py           # BASE_URL, credenciales por entorno y deptos E2E
│       ├── api_client.py       # requests.Session + Bearer + GET/POST/PUT/DELETE
│       └── polling.py          # esperar_hasta_que: reintentos, éxito temprano, timeout
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

# solo el feature de onboarding asíncrono del Punto 4
.venv/bin/behave features/onboarding.feature
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
  (`TESTS-humo.xml`, `TESTS-seguridad.xml`, `TESTS-onboarding.xml`).
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
3. Se espera con `esperar_hasta_que` (éxito temprano, reintentos cada 2 s,
   hasta ~30 s) la notificación de `usuario.creado` en
   `GET /notificaciones/{id}` y se extrae de su mensaje el token de
   activación.
4. `POST /auth/reset-password` activa la cuenta con `E2E_USER_PASSWORD`
   (default `User1234`, no es un secreto real).
5. `POST /auth/login` devuelve el access token USER real, que se usa como
   Bearer en el resto del escenario.

IDs únicos: `before_scenario` genera `context.run_id` (uuid4) y todos los
datos llevan el sufijo (`E2E-P3-<run_id>`, `E2E-P3-USER-<run_id>`,
`e2e-p3-*-<run_id>@empresa.com`), así que dos corridas o dos escenarios
nunca chocan. El departamento compartido `E2E-P3-DEPT` se crea una sola vez
(la primera corrida) y luego se reutiliza.

## Onboarding asíncrono (Punto 4)

`features/onboarding.feature` verifica el ciclo de incorporación real contra
el stack levantado, en 5 escenarios independientes con `Antecedentes` (login
ADMIN + departamento `E2E-P4-DEPT` asegurado con el paso reutilizado del P3):

| Escenario | Qué verifica |
|---|---|
| El alta crea la cuenta del usuario en auth (eventualmente) | `POST /empleados` -> 201; polling hasta la notificación `SEGURIDAD` que auth publica (`usuario.creado`) tras persistir la cuenta, con reset token |
| El alta genera la notificación de bienvenida por el medio simulado (eventualmente) | polling hasta la notificación `BIENVENIDA` (destinatario email, `empleadoId`, mensaje y `fechaEnvio`) |
| El empleado nuevo establece su contraseña y puede iniciar sesión | reset token de la notificación -> `POST /auth/reset-password` -> 200; `POST /auth/login` -> 200 con rol USER y estado ACTIVA |
| El alta con un departamento inexistente es rechazada | `POST /empleados` con `departamentoId` inexistente -> **400** |
| El alta con campos obligatorios faltantes es rechazada | `POST /empleados` sin `email` ni `numeroEmpleado` -> **400** |

Códigos observados contra el stack levantado (no inventados):

| Caso | Endpoint | Código |
|---|---|---|
| Alta válida (ADMIN) | `POST /empleados` | 201 |
| Cuenta creada por auth (evento `usuario.creado`) | `GET /notificaciones/{empleadoId}` | 200 con notificación `SEGURIDAD` + token |
| Bienvenida del medio email simulado | `GET /notificaciones/{empleadoId}` | 200 con notificación `BIENVENIDA` |
| Establecer password con el token | `POST /auth/reset-password` | 200 |
| Login con la password establecida | `POST /auth/login` | 200 |
| Departamento inexistente | `POST /empleados` | **400** (`El departamento con id '...' no existe`) |
| Campos faltantes (`email`, `numeroEmpleado`) | `POST /empleados` | **400** (`Datos inválidos: ... obligatorio`) |

"auth creó el usuario" no se puede leer por HTTP: auth-service no expone un
listado de usuarios. La evidencia observable es la notificación `SEGURIDAD`
del evento `usuario.creado`, que auth publica justo después de persistir la
cuenta `SUSPENDIDA_TEMPORAL` y que incluye el reset token. El empleado es
único por escenario (`E2E-P4-<run_id>`), así que esa notificación no puede
venir de otro alta.

Independencia: cada escenario usa el `run_id` (uuid4) de `before_scenario` en
`id`, `email` y `numeroEmpleado`; los escenarios inválidos agregan sufijos
(`-DEPT`, `-FALTANTE`). El único estado compartido es el departamento
`E2E-P4-DEPT`, idempotente. Ejecución:

```bash
cd e2e-tests
ADMIN_EMAIL=... ADMIN_PASSWORD=... .venv/bin/behave features/onboarding.feature
```

## Polling

`features/support/polling.py` expone el helper real del Punto 4:

```python
esperar_hasta_que(
    condicion,                 # callable sin args: sondea y devuelve algo truthy si ya ocurrió
    descripcion="la condición",
    max_intentos=15,
    intervalo_ms=2000,
    timeout_s=30.0,
)  # -> primer resultado truthy; TimeoutException con diagnóstico si se agota
```

Diseño y parámetros elegidos:

* **Éxito temprano**: la condición se evalúa de inmediato; si el evento ya fue
  procesado (caso habitual, <1 s) el escenario continúa sin penalización.
* **Reintentos acotados**: 15 intentos cada 2 s = ~28 s en el peor caso,
  dentro del techo global de 30 s; tolera la latencia de RabbitMQ + los
  consumidores sin quedarse corto si el stack está ocupado.
* **Balance velocidad/carga**: sondear cada 2 s agrega poca carga a un flujo
  cuyo evento típico tarda <1 s; un intervalo más agresivo no vería novedades
  antes porque el consumidor es el cuello de botella, y sí multiplicaría las
  peticiones.
* **Diagnóstico**: `TimeoutException` (subclase de `AssertionError`) informa
  descripción, intentos, tiempo transcurrido, intervalo, timeout y último
  resultado/error HTTP.
* **Sin `time.sleep` en steps**: la única espera es el intervalo entre
  reintentos del helper; ningún paso duerme un tiempo fijo. También reintenta
  `requests.RequestException` (hipo transitorio del gateway).
* `esperarHastaQue` existe como alias camelCase del nombre del enunciado.

La activación USER del P3 (`auth_steps.py`) y los pasos `eventualmente` del P4
(`onboarding_steps.py`) usan el mismo helper.
