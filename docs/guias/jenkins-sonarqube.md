# Guía: Jenkins y SonarQube

Volver al [README](../../README.md)

## 1. Levantar CI

```bash
docker compose up -d --build jenkins sonarqube sonar-db registry
```

| Herramienta | URL | Acceso |
|---|---|---|
| Jenkins | http://localhost:9090 | `admin` / archivo `secrets/jenkins_admin_password` |
| SonarQube | http://localhost:9000 | `admin`; la contraseña de fábrica se cambia en el primer ingreso |
| Registry | http://localhost:5000/v2/_catalog | sin autenticación |

### Permiso del socket de Docker (automático)

Jenkins construye imágenes y levanta el stack E2E con el Docker del host
(socket montado). En Docker Desktop el socket llega como `root:root`; el
entrypoint de la imagen (`jenkins/docker-socket-entrypoint.sh`) lo entrega al
grupo `docker` en cada arranque y luego ejecuta Jenkins como el usuario
`jenkins`. No hay pasos manuales.

### Memoria

Jenkins (`-Xmx512m`, límite 1 GB) y SonarQube (tres procesos Java acotados,
límite 1,8 GB) tienen la memoria limitada en el compose para que el stack
completo quepa en un equipo de 8 GB. El E2E de Jenkins levanta una segunda
copia de la aplicación: en equipos con poca memoria, ejecutarlo con la
observabilidad apagada.

## 2. Configuración como código

| Archivo | Qué configura |
|---|---|
| `jenkins/Dockerfile` | Jenkins LTS + plugins (pipeline, docker-workflow, JCasC, job-dsl, sonar, junit, coverage, htmlpublisher, lockable-resources) + cliente Docker |
| `jenkins/casc.yaml` | Jobs `empleados-service` y `vacaciones-service` (Job DSL, `pollSCM` cada minuto, rama del repo montado en `/workspace`) y credenciales `sonar-token` y `jwt-secret` |
| `jenkins/init.groovy.d/create-admin.groovy` | Usuario `admin` con la contraseña del Docker secret; sin asistente de instalación |
| `empleados/Jenkinsfile`, `vacaciones/Jenkinsfile` | Pipelines declarativos versionados junto al código |

Después de reiniciar Jenkins, JCasC vuelve a crear los jobs y sus triggers
quedan inactivos hasta la primera ejecución: hacer **Build Now** una vez en
cada job.

## 3. SonarQube (una sola vez por volumen nuevo)

1. Entrar a http://localhost:9000 con `admin` y la contraseña de fábrica de
   la imagen; SonarQube obliga a cambiarla.
2. **Quality gate de cobertura**: *Quality Gates* → *Create* → nombre
   `reto7-70` → *Add Condition* → *On Overall Code* → **Coverage is less than
   70** → guardar.
3. **Asignarlo a los proyectos**: SonarQube 9.9 solo permite marcar como
   *default* un gate que cumpla *Clean as You Code*; este no lo hace a
   propósito (solo exige cobertura). Se asigna por proyecto:
   - *Projects* → *Create Project* → *Manually* → claves exactas
     `empleados-service` y `vacaciones-service` (si aún no existen).
   - En el gate → sección *Projects* → pestaña *Without* → marcar ambos.
   - Comprobar en cada proyecto: *Project Settings* → *Quality Gate* →
     "Always use a specific Quality Gate".
4. **Token para Jenkins**: avatar → *My Account* → *Security* → *Generate
   Tokens* (tipo *Global Analysis Token*) → copiar el valor en `.env` como
   `SONAR_TOKEN=...` (es la variable `SONAR_TOKEN`, no `SONAR_DB_PASSWORD`).
5. Recrear Jenkins para que cargue el token: `docker compose up -d jenkins`.

## 4. Etapas del pipeline

`Checkout → Build → Test → SonarQube (+ Quality Gate) → Package → E2E Tests`

| Etapa | Qué hace | Falla si |
|---|---|---|
| Checkout | Clona la rama desde el repo montado | — |
| Build | Compila sin tests (`mvn package`, `bundle install`) | no compila |
| Test | Unitarias + integración; publica JUnit y cobertura | (UNSTABLE si hay pruebas en rojo) |
| SonarQube | Análisis estático + cobertura; `sonar.qualitygate.wait=true` | el gate no pasa (**cobertura < 70 %**) |
| Package | Imagen Docker → `localhost:5000/<servicio>:<build>` y `:latest` | falla el build o el push |
| E2E Tests | Stack aislado (`-p reto7-e2e`) con secretos efímeros, suite BDD, logs archivados, `down -v` | el stack no levanta (UNSTABLE si fallan escenarios) |

Los E2E de los dos jobs se serializan con `lock('e2e-stack')` porque comparten
puertos.

## 5. Reportes publicados

| Reporte | Dónde se ve en Jenkins |
|---|---|
| Pruebas unitarias/integración (JUnit XML) | pestaña **Test Result** |
| Cobertura (JaCoCo / Cobertura XML) | pestaña **Coverage** |
| Escenarios BDD (JUnit XML) | **Test Result** |
| Reporte BDD navegable (`cucumber.html`) | enlace **Reporte BDD** |
| Logs del stack E2E | artefacto `docker-logs.txt` |
| Análisis estático | http://localhost:9000, proyecto del servicio |

## 6. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `Not authorized. Please check the properties sonar.login` | token inválido (SonarQube recreado o token en otra variable) | generar token y ponerlo en `SONAR_TOKEN`; recrear Jenkins |
| `permission denied ... docker.sock` | la imagen de Jenkins es anterior al entrypoint automático | `docker compose up -d --build jenkins` |
| E2E: puerto 18080 ocupado | quedó un stack E2E de un build cortado | `docker compose -p reto7-e2e down -v` |
| Builds que se relanzan solos | abortar dispara `pollSCM` cada minuto | dejar terminar el build o desactivar el trigger temporalmente |
