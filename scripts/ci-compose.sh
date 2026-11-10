#!/bin/sh
# Wrapper de compose para CI (Reto 7 P4): proyecto aislado reto7-e2e.
# Uso: scripts/ci-compose.sh [-r] <comando compose...>
#   -r  agrega docker-compose.registry.yml (etapa Package, con TAG en entorno)
# Requiere: .ci-tools/docker-compose (scripts/fetch-compose.py), CWD en la raíz
# y JWT_SECRET exportado por el llamador (en Jenkins: credencial 'jwt-secret'
# re-exportada; el repo no trae .env y el compose lo exige). Sin secretos en git.
set -eu
REG=""
if [ "${1:-}" = "-r" ]; then REG="-f docker-compose.registry.yml"; shift; fi
# shellcheck disable=SC2086
: "${JWT_SECRET:?JWT_SECRET debe estar exportado (credencial jwt-secret en Jenkins)}"

# Proyecto Final — cero secretos: el workspace de CI no tiene .env ni secrets/.
# Cada contraseña que falte se genera aleatoria para ESTA invocación (el stack
# E2E es desechable y se baja con 'down -v'); docker-compose.e2e.yml las pasa
# a los contenedores como secretos "environment:". Nunca se imprimen.
ci_random() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
for var in RABBITMQ_PASSWORD SONAR_DB_PASSWORD GRAFANA_ADMIN_PASSWORD JENKINS_ADMIN_PASSWORD \
           DB_AUTH_PASSWORD DB_EMPLEADOS_PASSWORD DB_DEPARTAMENTOS_PASSWORD \
           DB_NOTIFICACIONES_PASSWORD DB_PERFILES_PASSWORD DB_VACACIONES_PASSWORD; do
  eval "cur=\${$var:-}"
  if [ -z "$cur" ]; then
    eval "$var=\$(ci_random)"
    export "${var?}"
  fi
done
exec .ci-tools/docker-compose -p reto7-e2e -f docker-compose.yml -f docker-compose.e2e.yml $REG "$@"
