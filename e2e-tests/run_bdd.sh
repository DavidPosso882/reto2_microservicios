#!/usr/bin/env bash
#
# Wrapper único de la suite E2E BDD (Reto 6, Punto 6).
#
# Simplifica la corrida documentada en README.md y e2e-tests/README.md:
#   - se coloca en e2e-tests/ sin importar el cwd desde el que se invoque;
#   - exporta defaults no secretos (BASE_URL) y las credenciales ADMIN del
#     bootstrap de demo del stack (README raíz § "Cómo obtener un token"),
#     siempre sobreescribibles por variables de entorno (en CI/Jenkins Reto 7
#     se inyectan las reales);
#   - propaga el exit code de behave tal cual (0 = verde, 1 = fallo/error de
#     test), de modo que sirve como gate de CI.
#
# Uso:
#   ./run_bdd.sh                              # suite completa (18 escenarios)
#   ./run_bdd.sh features/seguridad.feature   # un feature puntual
#   ADMIN_EMAIL=otro@empresa.com ADMIN_PASSWORD=... ./run_bdd.sh
#
# Los reportes quedan en e2e-tests/reports/ (gitignored):
#   cucumber.json, cucumber.html, TESTS-<feature>.xml
set -uo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${ADMIN_EMAIL:-}" || -z "${ADMIN_PASSWORD:-}" ]]; then
    echo "run_bdd.sh: usando credenciales ADMIN de demo del bootstrap (README raíz §4);" \
         "exporta ADMIN_EMAIL/ADMIN_PASSWORD para apuntar a otro stack." >&2
fi

export BASE_URL="${BASE_URL:-http://localhost:8080}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@empresa.com}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Admin123!}"

if [[ ! -x .venv/bin/behave ]]; then
    echo "run_bdd.sh: falta el venv local. Crearlo con:" >&2
    echo "  python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 127
fi

exec .venv/bin/behave "$@"
