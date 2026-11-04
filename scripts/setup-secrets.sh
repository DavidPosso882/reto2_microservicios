#!/usr/bin/env bash
# Genera la configuración secreta LOCAL (una sola vez por clon).
# Crea .env desde .env.example y genera JWT_SECRET + secrets/jwt_secret.txt.
# Idempotente: nunca sobrescribe valores ya generados.
# Lo generado NUNCA se versiona (.gitignore: .env, secrets/).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v openssl >/dev/null 2>&1 || { echo "ERROR: openssl no instalado" >&2; exit 1; }

# 1. .env desde la plantilla (solo si no existe).
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Creado .env desde .env.example"
fi

# 2. JWT_SECRET: generar solo si es placeholder o vacío.
if grep -qE '^JWT_SECRET=(__GENERAR_CON.*__|)$' .env; then
  JWT="$(openssl rand -hex 32)"
  # Escape para sed con delimitador |
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${JWT}|" .env
  echo "JWT_SECRET generado en .env"
else
  echo "JWT_SECRET ya existe en .env (no se toca)"
fi

# 3. Espejo file-based para futuro Docker Compose Secrets / Vault.
mkdir -p secrets
JWT_ACTUAL="$(grep '^JWT_SECRET=' .env | cut -d= -f2)"
if [[ ! -f secrets/jwt_secret.txt ]]; then
  printf '%s' "$JWT_ACTUAL" > secrets/jwt_secret.txt
  chmod 600 secrets/jwt_secret.txt
  echo "Creado secrets/jwt_secret.txt (modo 600)"
fi

echo "OK. Siguientes pasos:"
echo "  - Completar TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env (alertas T6)."
echo "  - Levantar: docker compose up --build"
