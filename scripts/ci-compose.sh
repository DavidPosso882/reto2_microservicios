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
exec .ci-tools/docker-compose -p reto7-e2e -f docker-compose.yml $REG "$@"
