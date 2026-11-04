# Guía: alertas a Telegram

## 1. Crear el bot y obtener el chat_id

1. Hablar con `@BotFather` → `/newbot` → guardar el **token** (`123456:ABC...`).
2. Abrir el bot y pulsar **START** (sin esto, Telegram responde `chat not found`).
   Para un grupo: agregar al bot como miembro (el ID suele empezar con `-100`).
3. Obtener el ID: tras el START, el bot ya "ve" el chat. Pedir a un bot como
   `@userinfobot` el ID, o usar `getUpdates` de la Bot API.

## 2. Conectarlo (sin tocar git)

```bash
# 1. Valores solo en el .env local (nunca en git)
#    TELEGRAM_BOT_TOKEN=123456:ABC...
#    TELEGRAM_CHAT_ID=123456789
# 2. Generar el contact point y reiniciar Grafana
python3 scripts/grafana-set-telegram.py
# 3. Probar: Grafana → Alerting → Contact points → reto8-telegram → Test
```

Cada `docker compose up -d --force-recreate grafana` re-aprovisiona desde el
fichero generado: re-ejecutar el script después (lee el mismo `.env`).

## 3. Formato de los mensajes (plantilla propia)

El receiver define `message` en `contact-points.yml.template`: estado con
icono (🔴/🟢), nombre de la alerta, `Servicio:` (etiqueta `job`, con respaldo
`—`), `Resumen:`, `Origen:` (regla), `Dashboard:` (solo si la regla lo tiene)
`Silenciar:` y `Consola:`. Sin el dump crudo de valores: el dashboard tiene
las gráficas. Cambios al template exigen re-generar, reiniciar Grafana y un
drill con regla temporal (verificado firing + resolved en ambos cambios).

## 4. Limitación conocida (hallazgo T6)

Grafana **no arranca** si el `chat_id` numérico va como `$VAR` en el YAML
(`cannot unmarshal number into Config.chatid`) ni acepta reescritura por API
de objetos con `provenance: file`. Por eso el repo versiona
`contact-points.yml.template` y el script genera `contact-points.yml`
(ignorado por git) con los valores entre comillas. Verificado: bootea y envía.

## 4. Seguridad del bot

- El bot es **solo-envío**: Grafana manda al `chat_id` fijo del servidor; por
  chat no hay comandos ni nada que operar.
- Privacidad de grupo activada (solo lee comandos) y **sin webhook**: nadie
  intercepta las alertas.
- Si el token se filtra: `@BotFather` → `/revoke`, actualizar el `.env` y
  re-ejecutar el script. Rotación de JWT: `scripts/setup-secrets.sh` + recrear.
