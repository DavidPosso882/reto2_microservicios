# Guía: CI con Jenkins + SonarQube

## Servicios base

Jenkins (`:9090`, admin según `jenkins/init.groovy.d`), SonarQube (`:9000`,
`admin/admin` la primera vez) y Registry (`:5000`) salen con el compose. Los
7 jobs se aprovisionan solos (JCasC, `jenkins/casc.yaml`, rama `main`).

## Primer arranque (necesario para que corran los pipelines)

Los jobs usan el repo local (`file:///workspace`, rama `main`): sin git no hay
polling. Tras descomprimir:

```bash
git init -b main && git add -A && git commit -m "entrega inicial"
```

Luego generar el token Sonar (SonarQube → My Account → Security → token tipo
Global Analysis) y ponerlo en el `.env` como `SONAR_TOKEN` (JCasC lo inyecta
como credencial `sonar-token`; `jwt-secret` sale de `JWT_SECRET`). Cada push
a `main` dispara por polling (~2 min) el pipeline del servicio cambiado.

`microservicios/<servicio>/Jenkinsfile`: Checkout → Build → Test → SonarQube
(`qualitygate.wait=true`: QG rojo = FAILURE) → Package (imagen a
`localhost:5000/<servicio>:<BUILD_NUMBER>` y `:latest` vía
`docker-compose.registry.yml`) → E2E (stack aislado + `e2e-tests/run_bdd.sh`).

Credenciales Jenkins (vienen del `.env`, nunca en git): `sonar-token`
(`SONAR_TOKEN`), `jwt-secret` (`JWT_SECRET` para los stacks E2E desechables).

## Regla de veredictos

- Tests rojos → **UNSTABLE** (con reporte XML) o **FAILURE** (gate por exit code).
- Cobertura <70% o Quality Gate rojo → **FAILURE**.
- Gates: Node (`--test-coverage-lines/functions/branches=70` + LCOV a Sonar),
  Python (`--cov-fail-under=70`), Go (alcance unitario ≥70% vía `cover -func`),
  Java (JaCoCo), Ruby (stdlib). Ver `docs/arquitectura.md` § Cobertura.

## Reportes (contrato)

`<servicio>/reports/junit.xml` + cobertura (`target/site/jacoco/jacoco.xml` en
Java, `coverage/lcov.info` en Node, `reports/coverage.xml` en Python/Ruby,
`coverage.out` en Go); `e2e-tests/reports/TESTS-*.xml` + `cucumber.json/html`.
Todo gitignored: Jenkins los archiva, nunca se versionan.
