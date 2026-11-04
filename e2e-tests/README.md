# e2e-tests — Pruebas E2E BDD (Reto 6)

Proyecto **independiente** del stack (no toca compose, `.env` ni servicios):
pruebas de extremo a extremo en Python con **Behave** (Gherkin en español) y
**requests**, apuntando al **gateway** en `http://localhost:8080`. Un solo
comando (`./run_bdd.sh`, wrapper que fija defaults y propaga el exit code de
Behave) deja **3 reportes**: JUnit XML, Cucumber JSON y HTML navegable.

Estado P2..P6: humo verde (1 escenario), seguridad RBAC verde (4),
onboarding asíncrono verde (5), vacaciones y ciclo de vida (4) y offboarding
(4). Total: **18 escenarios** independientes en 5 features (**116 steps**),
verificados en **3 corridas consecutivas** (5 features / 18 escenarios / 116
steps, exit 0). El polling real vive en `features/support/polling.py` y lo
comparten la activación USER del P3, los escenarios `eventualmente` del P4,
el ciclo del scheduler del P5 y las comprobaciones negativas del offboarding;
los escenarios RBAC siguen siendo síncronos (sin polling).

## Estructura

```text
e2e-tests/
├── behave.ini                  # formatter JSON + HTML + junit + pretty a stdout
├── requirements.txt            # behave, behave-html-formatter, requests (fijadas)
├── run_bdd.sh                  # wrapper: defaults + exit code de behave
├── features/
│   ├── environment.py          # hooks: contexto limpio + run_id único por escenario
│   ├── humo.feature            # escenario de humo (# language: es)
│   ├── seguridad.feature       # RBAC: 401 sin token, 403 USER, ADMIN 200/201/200
│   ├── onboarding.feature      # P4: alta -> auth + notificación + reset/login, 5 escenarios
│   ├── vacaciones.feature      # P5: programación, rechazos y ciclo suspender/reactivar
│   ├── offboarding.feature     # P5: retiro, bloqueo permanente, recuperación y auditoría
│   ├── steps/
│   │   ├── common_steps.py     # sistema operativo / código de respuesta
│   │   ├── auth_steps.py       # login, activación USER real y empleado activo del P5
│   │   ├── seguridad_steps.py  # pasos RBAC del Punto 3 (login/depto reutilizados)
│   │   ├── onboarding_steps.py # pasos asíncronos del Punto 4 (eventualmente)
│   │   ├── vacaciones_steps.py # programación, rechazos y ciclo del scheduler (P5)
│   │   └── offboarding_steps.py# baja, bloqueo permanente y auditoría (P5)
│   └── support/
│       ├── config.py           # BASE_URL, credenciales por entorno y deptos E2E
│       ├── api_client.py       # requests.Session + Bearer + GET/POST/PUT/DELETE
│       └── polling.py          # esperar_hasta_que: reintentos, éxito temprano, timeout
└── reports/                    # cucumber.json + cucumber.html + TESTS-*.xml (gitignored)
```

## BDD y escenarios cubiertos

**BDD** (Behavior-Driven Development) expresa cada prueba como comportamiento
observable en lenguaje natural: Gherkin (`Característica > Escenario >
Dado/Cuando/Entonces`) en español (`# language: es`). El `.feature` es a la vez
especificación legible por negocio y prueba ejecutable; el paso se implementa
en Python (`features/steps/`) y el estado se aísla por escenario
(`environment.py` + `run_id` uuid4).

Se eligió **Behave + requests** porque el equipo ya usa Python (mismo lenguaje
que pytest en `notificaciones`), Gherkin `es` es nativo, `requests` resuelve el
polling sin dependencias extra y Behave trae JUnit XML / Cucumber JSON de
fábrica (HTML con `behave-html-formatter`). Alternativas descartadas:
pytest-bdd (formatters menos maduros), Robot Framework (DSL propio, no Gherkin
puro) y Cucumber-JVM (otra JVM para un cliente HTTP).

| Feature | Escenarios | Punto | Qué cubre |
|---|---|---|---|
| `humo.feature` | 1 | P2 | gateway vivo y operativo (`GET /health` 200) |
| `seguridad.feature` | 4 | P3 | 401 sin/invalid/malformed token, 403 USER, 201/200 ADMIN |
| `onboarding.feature` | 5 | P4 | alta → cuenta auth + BIENVENIDA (eventualmente) → reset/login; 400 de validación |
| `vacaciones.feature` | 4 | P5 | programación + notificación, 400 de fechas/solape, ciclo del scheduler suspender/reactivar |
| `offboarding.feature` | 4 | P5 | retiro + notificaciones, bloqueo permanente, recuperación sin efecto, auditoría |
| **Total** | **18** | | **116 steps** verdes en 3 corridas consecutivas |

Los detalles de cada flujo (códigos observados, polling, satélites del
scheduler) están en las secciones siguientes.

## Prerequisitos

| Herramienta | Versión usada | Para qué |
|---|---|---|
| Docker + Docker Compose | Compose v2 (stack verificado: 14/14 healthy) | levantar el sistema a probar (el stack vive fuera de esta suite) |
| Python | 3.11 (3.11.15 en la verificación) | venv local: Behave 1.3.3, requests 2.34.2, behave-html-formatter 0.9.10 |
| Java 21 + Maven 3.9 / Ruby 3.3 | — | opcional: suites de `empleados` y `vacaciones` (ver README raíz) |

## Ejecución exacta (a → d)

a) **Stack desplegado** (desde la raíz; es la única dependencia externa):

```bash
docker compose up --build -d
curl http://localhost:8080/health   # → 200 {"status":"ok","service":"api-gateway"}
# stack nuevo: bootstrapear el ADMIN (README raíz § "Cómo obtener un token")
```

b) **Entorno** (opcional; el wrapper ya trae defaults):

```bash
export BASE_URL=http://localhost:8080    # default del wrapper
export ADMIN_EMAIL=admin@empresa.com     # default demo del bootstrap
export ADMIN_PASSWORD=Admin123!          # default demo; en Jenkins se inyectan las reales
```

c) **Comandos** (la primera vez hay que crear el venv):

```bash
cd e2e-tests
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

./run_bdd.sh                               # suite completa: 18 escenarios
./run_bdd.sh features/seguridad.feature    # un feature puntual
./run_bdd.sh features/onboarding.feature   # P4
./run_bdd.sh features/vacaciones.feature   # P5
./run_bdd.sh features/offboarding.feature  # P5
```

d) **Reportes**: quedan en `e2e-tests/reports/` (gitignored): `cucumber.html`
(navegable, abrir en el navegador), `cucumber.json` y `TESTS-<feature>.xml`.
El contrato completo para Jenkins está en el README raíz.

`./run_bdd.sh` se coloca en `e2e-tests/` sin importar el cwd, exporta por
defecto `BASE_URL` y las credenciales ADMIN del bootstrap de demo (se
sobreescriben con `ADMIN_EMAIL`/`ADMIN_PASSWORD`) y hace `exec` de
`.venv/bin/behave`, así que propaga su exit code. Sin flags, Behave muestra
`pretty` en consola y deja los 3 reportes porque `behave.ini` equivale a
`behave -f json -o reports/cucumber.json -f html -o reports/cucumber.html
--junit --junit-directory reports`, añadiendo `pretty` a stdout.

## Variables de entorno

Las credenciales reales no se versionan: se inyectan por entorno y
`config.py` solo las lee cuando un paso las necesita. El wrapper
`./run_bdd.sh` trae como default las credenciales de **demo** del bootstrap
documentadas en el README raíz (se sobreescriben con `ADMIN_EMAIL` /
`ADMIN_PASSWORD`; en CI/Jenkins se inyectan las reales).

| Variable | Default | Uso |
|---|---|---|
| `BASE_URL` | `http://localhost:8080` | URL del gateway |
| `SMOKE_PATH` | `/health` | Endpoint público del humo |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | demo del bootstrap si no se definen (solo `run_bdd.sh`) | Login `"admin"` en Antecedentes |
| `USER_EMAIL` / `USER_PASSWORD` | (sin default) | Login `"user"` en Antecedentes (cuentas ya existentes) |
| `E2E_USER_PASSWORD` | `User1234` | Password de las cuentas USER sintéticas del P3 y del P5 (no es secreto) |
| `E2E_P5_SENUELOS` | `8` | Cuentas satélite que el ciclo del P5 programa en el mismo tick para ampliar la ventana de suspensión observable |
| `E2E_P5_LOGIN_INTERVAL_MS` | `100` | Intervalo de reintento del polling de login del P5 (ciclo y offboarding) |
| `E2E_P5_SCHEDULER_TIMEOUT_S` | `75` | Presupuesto máximo de espera del tick del scheduler (cubre el intervalo de 60 s + procesamiento) |
| `E2E_P5_REACTIVACION_TIMEOUT_S` | `20` | Presupuesto de espera del login 200 tras la suspensión (ocurre en el mismo tick) |
| `E2E_P5_VENTANA_NEGATIVA_S` | `10` | Ventana de evidencia de las comprobaciones negativas del offboarding |
| `HTTP_TIMEOUT` | `10` | Timeout HTTP en segundos |

Ejemplo local (el escenario de humo no necesita credenciales; seguridad sí):

```bash
cd e2e-tests
ADMIN_EMAIL=admin@empresa.com ADMIN_PASSWORD=... ./run_bdd.sh
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

## Reportes (contrato Reto 7)

Cada corrida deja en `reports/` (gitignored) los 3 formatos:

* `reports/cucumber.json` — Cucumber JSON con los 5 features (Jenkins lo usa
  como reporte de resultados del nivel E2E).
* `reports/cucumber.html` — HTML navegable de `behave-html-formatter`
  (características, escenarios y pasos con estado y duración); se abre
  directo en el navegador.
* `reports/TESTS-<feature>.xml` — JUnit XML por feature
  (`TESTS-humo.xml`, `TESTS-seguridad.xml`, `TESTS-onboarding.xml`,
  `TESTS-vacaciones.xml`, `TESTS-offboarding.xml`); suman **18 testcases**.

Además, la consola muestra el resultado con el formatter `pretty`.

Como el wrapper propaga el exit code de Behave (0/1) y los reportes son
estándar, Jenkins Reto 7 puede publicarlos sin parsers propios:

| Para | Archivo |
|---|---|
| Resultados E2E (JUnit) | `e2e-tests/reports/TESTS-*.xml` |
| Resultados E2E (Cucumber) | `e2e-tests/reports/cucumber.json` |
| Detalle navegable | `e2e-tests/reports/cucumber.html` |

El resto del contrato (empleados y vacaciones) está en la tabla del README
raíz; `run_bdd.sh` es el comando único de esta suite.

### Consistencia y gate de CI (verificación P6)

* **3 corridas consecutivas** de `./run_bdd.sh`: 5 features / 18 escenarios /
  116 steps passed, exit 0 en las 3; el JUnit XML sumó 18 testcases con 0
  failures y el HTML 116 steps `passed` / 0 `failed`.
* **Fallo simulado**: se cambió temporalmente un código esperado
  (`201`→`200` en `features/seguridad.feature`), `./run_bdd.sh
  features/seguridad.feature` devolvió **exit 1** con el mensaje
  `ASSERT FAILED: POST http://localhost:8080/empleados devolvió 201, se
  esperaba 200.`, dejó 1 `<failure>` en `reports/TESTS-seguridad.xml` y un
  `class="step failed"` en el HTML; el feature se revirtió (diff vacío).
  Sirve como prueba de que el comando es un gate real de CI.

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
ADMIN_EMAIL=... ADMIN_PASSWORD=... ./run_bdd.sh features/onboarding.feature
```

## Vacaciones y ciclo de vida de la cuenta (Punto 5)

`features/vacaciones.feature` cubre la programación, los rechazos reales y el
ciclo completo de suspensión/reactivación, en 4 escenarios independientes con
`Antecedentes` (login ADMIN + departamento `E2E-P5-DEPT` + empleado activo con
credenciales creadas desde cero):

| Escenario | Qué verifica |
|---|---|
| La programación exitosa se notifica eventualmente | `POST /vacaciones` -> **201** `PROGRAMADA`; polling hasta la notificación `VACACIONES` "Tus vacaciones fueron programadas desde ... hasta ..." |
| Las fechas incoherentes son rechazadas | `fechaFin` anterior a `fechaInicio` -> **400** con mensaje que nombra ambos extremos |
| El solapamiento es rechazado | segundo `POST` que pisa un período vigente -> **400** con `conflicto` = período en pugna |
| Ciclo completo del scheduler | período `hoy -> hoy`: polling hasta **401** (cuenta `SUSPENDIDA_TEMPORAL`), luego polling hasta **200** (reactivada), período `FINALIZADA` y notificaciones `CUENTA` de suspensión (`VACACIONES`) y reactivación (`FIN_VACACIONES`) |

Códigos observados contra el stack levantado (no inventados):

| Caso | Endpoint | Código |
|---|---|---|
| Programación válida | `POST /vacaciones` | 201 `PROGRAMADA` |
| Fechas incoherentes | `POST /vacaciones` | 400 `fechaFin (...) debe ser igual o posterior a fechaInicio (...)` |
| Solapamiento | `POST /vacaciones` | 400 `El período se solapa ...` + `conflicto` |
| Inicio de vacaciones | `POST /auth/login` | **401** (cuenta `SUSPENDIDA_TEMPORAL`) |
| Fin de vacaciones | `POST /auth/login` | **200** (cuenta `ACTIVA` de nuevo) |

### Control del tiempo: cómo inicia y termina un período sin esperar días

El scheduler de vacaciones (`vacaciones/app/scheduler.rb`) corre cada
`SCHEDULER_INTERVAL_S` segundos (default **60**, configurable por entorno) y
aplica las transiciones por FECHA con comparación inclusiva:
`PROGRAMADA` con `fechaInicio <= hoy` -> `EN_CURSO`, y `EN_CURSO` con
`fechaFin <= hoy` -> `FINALIZADA`. La estrategia de demo del Reto 5 es
`fechaInicio = fechaFin = hoy`.

Consecuencia medida en el stack real: **las dos transiciones de un período
`hoy -> hoy` ocurren en el mismo tick** (las notificaciones `vacaciones.iniciadas`
y `vacaciones.finalizadas` del mismo período quedaron a ~3.5 ms), de modo que la
ventana de `SUSPENDIDA_TEMPORAL` de una sola cuenta es de pocos milisegundos y
un polling HTTP no puede observarla de forma determinista. La prueba resuelve
el disparo sin acoplarse a la frecuencia ni tocar la infraestructura:

1. **Espera el tick con polling**: el paso del ciclo no duerme un tiempo fijo;
   sondea el login cada `E2E_P5_LOGIN_INTERVAL_MS` (default 100 ms) hasta ver
   el 401, con presupuesto `E2E_P5_SCHEDULER_TIMEOUT_S` (default **75 s**, que
   cubre cualquier fase del intervalo de 60 s). El escenario tarda lo que tarde
   el tick (típico 5-60 s), no un tiempo prefijado.
2. **Amplifica la ventana con cuentas satélite**: antes de programar el período
   del protagonista, el paso crea `E2E_P5_SENUELOS` (default **8**) cuentas
   satélite y las deja existir en auth-service (notificación `SEGURIDAD`); luego
   programa `hoy -> hoy` para el protagonista y **acto seguido** para los satélite,
   para que todas las transiciones caigan en el mismo tick. auth-service procesa
   los eventos en serie, así que la ventana de suspensión del protagonista se
   estira a ~cantidad × tiempo-de-procesamiento (medido: **~365 ms con 6+1**
   cuentas y **~480 ms con 8+1**), suficiente para que el polling de 100 ms vea el
   401 varias veces. Todo es HTTP público contra el gateway: sin SQL, sin broker,
   sin `sleep` fijo y sin endpoint de disparo manual (el servicio desplegado no
   lo expone; la tarea del Reto 5 lo había previsto pero no está implementado).
3. **Conocimiento explícito de la frecuencia**: el único acoplamiento es el
   timeout de 75 s para recibir el tick; si `SCHEDULER_INTERVAL_S` se sube por
   encima de ese presupuesto, se ajusta `E2E_P5_SCHEDULER_TIMEOUT_S` sin tocar
   los escenarios. La prueba nunca asume *cuándo* ocurre el tick dentro del
   intervalo.

Compromiso documentado: si el tick cayera justo en la ventana de ~30 ms entre
el `POST` del protagonista y el primero de los satélite, la ventana del
protagonista quedaría sin amplificar y el escenario fallaría con el
diagnóstico de timeout (probabilidad teórica ~0.05 %). El mensaje de error
indica reejecutar el escenario y revisar los consumidores de RabbitMQ.

## Offboarding (Punto 5)

`features/offboarding.feature` cubre la desvinculación completa en 4
escenarios independientes con el mismo `Antecedentes` del P5:

| Escenario | Qué verifica |
|---|---|
| La desvinculación se registra y notifica | `DELETE /empleados/{id}` -> **200** `RETIRADO` + `fechaRetiro`; polling hasta `DESVINCULACION` y hasta la `CUENTA` de baja permanente (`RETIRO`) |
| El retirado no puede volver a entrar | polling hasta **401** (evento de retiro procesado) + ventana negativa en la que cualquier 200 falla |
| La recuperación no reactiva | `POST /auth/recover-password` -> **200 uniforme**; polling negativo: no aparece notificación `SEGURIDAD` nueva; el reset token anterior responde **401**; login **401** |
| Auditoría | `GET /empleados?estado=RETIRADO` -> **200** e incluye el empleado con `estado=RETIRADO` y `fechaRetiro` (baja lógica, nunca se borra) |

Códigos observados contra el stack levantado:

| Caso | Endpoint | Código |
|---|---|---|
| Baja lógica (ADMIN) | `DELETE /empleados/{id}` | 200 `RETIRADO` + `fechaRetiro` |
| Login del retirado | `POST /auth/login` | **401** (uniforme para desconocido/desactivado/clave mala) |
| Recuperación del retirado | `POST /auth/recover-password` | **200 uniforme**, sin publicar `usuario.recuperacion` |
| Reset con token anterior al retiro | `POST /auth/reset-password` | **401** (`El token es inválido o expiró`) |
| Consulta de auditoría | `GET /empleados?estado=RETIRADO` | 200 con el registro retirado |

### Polling negativo (distinguir "todavía no" de "nunca")

Verificar que un empleado "eventualmente no puede entrar" es una condición
negativa y se resuelve así:

* **Bloqueo por retiro**: se sondea el login con la contraseña correcta hasta
  ver 401, con timeout explícito de 30 s. El estado inicial comprobado es 200
  (el Antecedentes inicia sesión), así que un timeout devolviendo 200 se
  diagnostica como "auth-service aún no procesó `empleado.retirado`" y falla;
  no se aprueba por accidente.
* **Permanencia**: tras el 401, una ventana de observación
  (`E2E_P5_VENTANA_NEGATIVA_S`, default 10 s) muestrea el login varias veces;
  si algún intento devuelve 200, el escenario falla al instante (la baja debe
  ser permanente). Si la ventana se agota sin un 200, la ausencia queda
  evidenciada dentro del presupuesto (no hay forma de probar "para siempre" en un
  test finito; se documenta el límite).
* **Sin token nuevo de recuperación**: antes de `recover-password` se
  fotografían los ids de las notificaciones `SEGURIDAD`; durante la ventana se
  comprueba que no aparece ninguna nueva. La prueba definitiva complementaria
  es funcional: el reset token emitido antes del retiro responde **401**.
* Estas comprobaciones reutilizan `esperar_hasta_que`: la aparición indebida
  (un 200, un token nuevo) es la condición truthy que hace fallar; la
  `TimeoutException` se interpreta como "no ocurrió en la ventana".

### Reutilización de pasos y precondiciones complejas

El `Antecedentes` de ambos features encadena pasos ya existentes y solo agrega
una precondición nueva:

| Paso | Origen |
|---|---|
| `Dado que inicio sesión como "admin"` | P3 (`auth_steps.py`), sin cambios |
| `Y que existe el departamento "E2E-P5-DEPT"` | P3 (`seguridad_steps.py`), parametrizado por id |
| `Entonces respuesta código N` | P2 (`common_steps.py`), sin cambios |
| `Y que existe un empleado activo con credenciales establecidas` | Nuevo en `auth_steps.py`; internamente reutiliza el mismo flujo real del P3/P4 (alta ADMIN -> notificación `SEGURIDAD` -> reset con token -> login 200) mediante los helpers `_activar_cuenta`/`_esperar_reset_token` y el polling del P4 |

Independencia: el empleado protagonista es `E2E-P5-<run_id>`; los satélite son
`E2E-P5-SENUELO-<run_id>-<n>`; el único estado compartido es el departamento
`E2E-P5-DEPT`, idempotente. Ejecución:

```bash
cd e2e-tests
ADMIN_EMAIL=... ADMIN_PASSWORD=... ./run_bdd.sh features/vacaciones.feature
ADMIN_EMAIL=... ADMIN_PASSWORD=... ./run_bdd.sh features/offboarding.feature
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

La activación USER del P3 (`auth_steps.py`), los pasos `eventualmente` del P4
(`onboarding_steps.py`) y el Punto 5 completo (`vacaciones_steps.py`,
`offboarding_steps.py`) usan el mismo helper, con presupuestos por caso:

* **Eventos de cuenta y propagación** (notificaciones, réplica local de
  vacaciones, cuentas satélite): intervalos cortos (500 ms - 1 s) y techos de
  15-30 s, porque el evento típico se materializa en <1 s.
* **Ciclo del scheduler**: el login se sondea cada `E2E_P5_LOGIN_INTERVAL_MS`
  (default 100 ms) hasta el **401**, con presupuesto
  `E2E_P5_SCHEDULER_TIMEOUT_S` (default 75 s) para cubrir la espera del tick
  de 60 s. La reactivación posterior usa un presupuesto corto
  (`E2E_P5_REACTIVACION_TIMEOUT_S`, default 20 s) porque ocurre en el mismo
  tick.
* **Polling negativo** ("eventualmente NO puede entrar"): la condición del
  helper devuelve un valor truthy cuando ocurre lo indebido (un login 200 en
  el retirado, una notificación SEGURIDAD nueva en la recuperación) y la
  `TimeoutException` se interpreta como "no ocurrió dentro de la ventana"
  (`E2E_P5_VENTANA_NEGATIVA_S`, default 10 s). Así se distingue "todavía no se
  procesó" (los sondeos previos devolvían el estado esperado y el evento sí
  aparece) de "nunca se procesará dentro del presupuesto" (timeout, con el
  diagnóstico en el mensaje de fallo).
