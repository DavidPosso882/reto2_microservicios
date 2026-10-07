# e2e-tests — Pruebas E2E BDD (Reto 6)

Proyecto **independiente** del stack (no toca compose, `.env` ni servicios):
pruebas de extremo a extremo en Python con **Behave** (Gherkin en español) y
**requests**, apuntando al **gateway** en `http://localhost:8080`.

Estado P2: humo verde (1 escenario). El polling de eventos asíncronos queda
para P4 (ver `features/support/polling.py`).

## Estructura

```text
e2e-tests/
├── behave.ini                  # formatter JSON + junit + pretty a stdout
├── requirements.txt            # behave, requests (versiones fijadas)
├── features/
│   ├── environment.py          # hooks: contexto limpio por escenario
│   ├── humo.feature            # escenario de humo (# language: es)
│   ├── steps/
│   │   ├── common_steps.py     # sistema operativo / código de respuesta
│   │   └── auth_steps.py       # login para Antecedentes (Background)
│   └── support/
│       ├── config.py           # BASE_URL y credenciales por entorno
│       ├── api_client.py       # requests.Session + Bearer + last_response
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
| `USER_EMAIL` / `USER_PASSWORD` | (sin default) | Login `"user"` en Antecedentes |
| `HTTP_TIMEOUT` | `10` | Timeout HTTP en segundos |

Ejemplo local (el escenario de humo no necesita credenciales):

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

* `reports/cucumber.json` — formatter JSON (estilo cucumber).
* `reports/TESTS-humo.xml` — JUnit XML.
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

## Polling

No se implementa en P2. `support/polling.py` queda como stub documentado que
falla explícitamente si se usa; el helper real (`wait_until(...)` con timeout
e intervalo) llega en P4 junto con los flujos asíncronos.
