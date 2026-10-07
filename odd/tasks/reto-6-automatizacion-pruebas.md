# ODD — Reto 6: Automatización de Pruebas

Branch: `reto-6-automatizacion-pruebas` (base: `reto-5-seguridad-jwt` @ e1fd460)
Worktree: `../reto2-reto6` (limpio, conserva `reto2-reto5` intacto para sustentación Reto 5)
Doc fuente: `reto6-automatizacion-de-pruebas.md` + `main - reto6.pdf`

## Objetivo
Pirámide completa: unitarias + integración + BDD en español contra sistema desplegado,
con reportes estándar listos para Jenkins + Sonar del Reto 7.

## Decisiones validadas (2026-10-07, usuario)
1. Base **reto-5-seguridad-jwt** (no reto-4): BDD necesita JWT/RBAC + scheduler.
2. BDD en **Python Behave + requests** en `e2e-tests/`. Motivo: equipo ya domina pytest,
   polling trivial, Gherkin `es` nativo, reportes `--junit --format json` simples.
3. Integración con **Testcontainers** (fidelidad máxima PG real). H2/SQLite actual miente
   en constraints y sintaxis. Costo aceptado: Docker exigido igual por el E2E.
4. Si hay duda/ambigüedad: **preguntar antes de asumir** (pedido explícito usuario).

## Tareas y estado
1. [x] Crear rama + worktree reto-6 desde reto-5 + este archivo de tareas
2. [ ] P1 unitarias+integración+cov (1.5pt): vacaciones Ruby + empleados Java, Testcontainers, JaCoCo+Surefire, mutación manual
3. [ ] P2 proyecto BDD Behave (0.5pt): estructura, World, env BASE_URL, humo 200
4. [ ] P3 seguridad RBAC (0.5pt): 4 escenarios (sin token, inválido, USER vs ADMIN)
5. [ ] P4 onboarding async (1.0pt): polling `eventualmente`, IDs únicos, independencia
6. [ ] P5 vacaciones+offboarding (1.0pt): ciclo suspender/reactivar + retiro + auditoría, control del tiempo
7. [ ] P6 reportes+docs (0.5pt): junit+cucumber json/html, 1 comando, 3 corridas, fallo simulado, tabla README contrato Reto 7
8. [ ] Verificación final + commit(s) unidad de trabajo

## Hallazgos exploración (2026-10-07, base reto-5)
- `empleados` Java 21 Maven: 8 ficheros test, surefire incluye `*IT` en `mvn test`, usa H2 en tests -> migrar integración a Testcontainers PG16. Falta JaCoCo en pom.
- `vacaciones` Ruby Sinatra minitest: `validaciones_test.rb` + `support/fakes.rb` (sin PG/Rabbit). Base ideal P1, falta tabla borde solapamiento + junit/simplecov.
- `notificaciones` Python pytest 8.3.4: 5 ficheros, conftest SQLite memory + CONSUMER_ENABLED=false. 54/54 histórico. Añadir `--junitxml --cov`.
- `perfiles` Go 1.26: `memory_test.go`, `api_test.go`, `consumer_test.go`. No tocar en P1 salvo que falte cobertura.
- `departamentos` + `gateway` Node `node --test` (+supertest en deptos). Gateway ya tiene 32/32 con auth en reto-5.
- `e2e-tests/` no existe: crear desde cero con behave.
- `.gitignore` actual ignora `*.md` excepto README, `target/`, `node_modules/`, `__pycache__/`, `.pytest_cache/`. Falta agregar `reports/`, `coverage/`, `coverage.xml`, `junit.xml`, `cucumber.json/html`.
- Riesgos: scheduler (intervalo por env + disparo manual solo ADMIN), polling negativo, limpieza entre escenarios, JWT_SECRET en E2E, exit code !=0 obligatorio.

## Convención reportes (contrato Reto 7, a respetar desde día 1)
```
<servicio>/reports/junit.xml + coverage.xml (o target/surefire + jacoco.xml en Java)
e2e-tests/reports/junit.xml + cucumber.json + cucumber.html
```

## Evidencia / commits
- Branch+worktree: `reto-6-automatizacion-pruebas` desde `e1fd460` (2026-10-07). Sin commits aún, a decisión del usuario.

## P1 — unitarias+integración+cov (2026-10-07, worker+verify)
- Vacaciones Ruby: 70 runs, 297 assertions, 0 failures (`ruby tests/run_all.rb`); cobertura stdlib 75.36% líneas (260/345). Tabla solapamiento: contiene/contenido/toca-1-día/idéntico/adyacente-no-solapa + incoherentes + pasadas + días inclusivos. Fakes puros, sin Docker.
- Empleados Java: `EmpleadoServiceMockitoTest` 11/11 (Mockito, sin Spring/Docker) + `EmpleadoRepositoryPostgresIT` 4/4 Testcontainers `postgres:16-alpine` con `init.sql` real. Full `mvn test`: 87 tests, 0 failures. JaCoCo 0.8.12: total 84.06% líneas (269/320), EmpleadoService 95.04% (134/141).
- Reportes: `vacaciones/reports/junit.xml` + `coverage/coverage.json` (+html), `empleados/target/surefire-reports/*.xml` + `target/site/jacoco/jacoco.xml`. `.gitignore` ampliado con `reports/`, `coverage/`, `junit.xml`, `cucumber.*`.
- Mutación manual: `fecha_fin < fecha_inicio` -> `>` en `validations.rb` detectada (6 failures, mensaje `Expected: 1 / Actual: 0` en `test_validacion_1`), revertida (`git diff vacaciones/app` vacío).
- Verificación independiente (verify): Ruby 70/297 exacto, Mockito 11/11 exacto, JaCoCo LINE 84.06% confirmado, surfaces solo P1. Full 87 no re-ejecutado por el verificador (solo subset 11), queda como pendiente de CI.
- Commit P1: `4383d0a` test(reto6) P1 unitarias vacaciones+empleados con Testcontainers y cobertura.
