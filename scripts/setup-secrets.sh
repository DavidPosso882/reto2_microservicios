#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup-secrets.sh — genera la configuración local SIN que ningún secreto
# viva en el repositorio (Proyecto Final, restricción 4: cero secretos).
#
# Qué hace (idempotente: no pisa lo que ya existe salvo con --rotate):
#   1. Crea .env desde .env.example si no existe.
#   2. Crea secrets/ con un archivo por secreto (Docker Compose secrets):
#        jwt_secret                  clave HMAC de los JWT (auth-service + gateway + Jenkins)
#        db_<servicio>_password      contraseña de cada PostgreSQL (6)
#        grafana_admin_password      contraseña del admin de Grafana
#        jenkins_admin_password      contraseña del usuario admin de Jenkins
#   3. Completa en .env las contraseñas de imágenes que no leen *_FILE
#      (RABBITMQ_PASSWORD, SONAR_DB_PASSWORD) si están vacías.
#
# Migración: si un secreto aún no tiene archivo pero el .env viejo traía su
# valor (JWT_SECRET, DB_*_PASSWORD), se reutiliza ese valor. Así los volúmenes
# ya inicializados siguen arrancando con la misma contraseña.
#
# Uso:
#   bash scripts/setup-secrets.sh            # genera lo que falte
#   bash scripts/setup-secrets.sh --rotate   # regenera TODOS los secretos
#
# Rotación (--rotate): los valores nuevos solo aplican a volúmenes nuevos.
# PostgreSQL, RabbitMQ y Grafana guardan la contraseña al inicializar su
# volumen, así que tras rotar hay que recrearlos (docker compose down -v,
# borra datos) o cambiar la contraseña dentro de cada uno (ALTER USER ...,
# rabbitmqctl change_password, grafana-cli admin reset-admin-password).
# El JWT_SECRET sí rota en caliente: docker compose up -d --force-recreate
# api-gateway auth-service jenkins (los tokens emitidos dejan de valer).
#
# Nunca imprime los valores generados.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ROTATE=0
if [ "${1:-}" = "--rotate" ]; then
  ROTATE=1
elif [ -n "${1:-}" ]; then
  echo "Uso: bash scripts/setup-secrets.sh [--rotate]" >&2
  exit 2
fi

# 32 bytes aleatorios en hexadecimal (64 caracteres): sin símbolos que
# rompan URLs AMQP, cadenas de conexión ni el parser de .env.
random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

# Valor actual de una variable en .env (vacío si no está).
env_value() {
  [ -f .env ] || return 0
  grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r' || true
}

# ── 1. .env ──────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  cp .env.example .env
  echo "✔ .env creado desde .env.example"
else
  echo "• .env ya existe (se conserva)"
fi

# ── 2. secrets/ ──────────────────────────────────────────────────────────────
mkdir -p secrets

# nombre_archivo:variable_del_.env_viejo_a_migrar
SECRETS="
jwt_secret:JWT_SECRET
db_auth_password:DB_AUTH_PASSWORD
db_empleados_password:DB_EMPLEADOS_PASSWORD
db_departamentos_password:DB_DEPARTAMENTOS_PASSWORD
db_notificaciones_password:DB_NOTIFICACIONES_PASSWORD
db_perfiles_password:DB_PERFILES_PASSWORD
db_vacaciones_password:DB_VACACIONES_PASSWORD
grafana_admin_password:GRAFANA_ADMIN_PASSWORD
jenkins_admin_password:JENKINS_ADMIN_PASSWORD
"

for entry in $SECRETS; do
  name="${entry%%:*}"
  legacy="${entry#*:}"
  file="secrets/$name"
  if [ -s "$file" ] && [ "$ROTATE" -eq 0 ]; then
    echo "• secrets/$name ya existe (se conserva)"
    continue
  fi
  value=""
  if [ "$ROTATE" -eq 0 ]; then
    value="$(env_value "$legacy")"
  fi
  if [ -n "$value" ]; then
    origen="migrado desde $legacy del .env"
  else
    value="$(random_secret)"
    origen="generado"
  fi
  # Sin salto de línea final: el contenido es exactamente el secreto.
  printf '%s' "$value" > "$file"
  # 644: el usuario interno de postgres/grafana (no root) debe poder leerlo;
  # en Compose sin Swarm los secretos son bind mounts y conservan permisos.
  chmod 644 "$file"
  echo "✔ secrets/$name $origen"
done

# ── 3. Contraseñas en .env (imágenes sin soporte *_FILE) ─────────────────────
for var in RABBITMQ_PASSWORD SONAR_DB_PASSWORD; do
  current="$(env_value "$var")"
  if [ -n "$current" ] && [ "$ROTATE" -eq 0 ]; then
    echo "• $var ya tiene valor en .env (se conserva)"
    continue
  fi
  value="$(random_secret)"
  if grep -qE "^$var=" .env; then
    # '|' como separador: el valor es hexadecimal, nunca lo contiene.
    sed -i.bak -E "s|^$var=.*|$var=$value|" .env && rm -f .env.bak
  else
    printf '\n%s=%s\n' "$var" "$value" >> .env
  fi
  echo "✔ $var generado en .env"
done

# Las variables migradas a secrets/ ya no deben quedar duplicadas en .env.
for entry in $SECRETS; do
  legacy="${entry#*:}"
  if grep -qE "^$legacy=" .env; then
    sed -i.bak -E "/^$legacy=/d" .env && rm -f .env.bak
    echo "✔ $legacy quitado de .env (ahora vive en secrets/)"
  fi
done

cat <<'EOF'

Listo. Siguiente paso:
  docker compose up --build

Notas:
  - secrets/ y .env están en .gitignore: nunca los subas al repositorio.
  - SONAR_TOKEN y TELEGRAM_* se completan a mano en .env (ver .env.example).
  - Credenciales de acceso: README.md § "Accesos por defecto".
EOF
