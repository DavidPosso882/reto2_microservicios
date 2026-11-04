"""Event -> notification mapping (CATALOGO_EVENTOS.md sections 3.1, 3.3, 3.8
plus the Reto 5 lifecycle events published by auth-service and the
vacaciones scheduler).

Security note: account payloads never carry passwords. `usuario.creado` /
`usuario.recuperacion` carry a short-lived reset token, which is the only
sensitive value ever rendered into the notification message (the PDF flow
requires echoing the token in the simulated send log); no code path logs a
password because no event contains one.
"""

import json
import logging
import os

from app.models import Notificacion

# Plantillas configurables (proyecto final): app/plantillas.json versionado
# (o ruta en PLANTILLAS_PATH). Editar textos sin tocar código; si el fichero
# falta o una clave no existe, se usa el texto built-in idéntico.
_PLANTILLAS_PATH = os.environ.get(
    "PLANTILLAS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantillas.json"),
)
_PLANTILLAS_CACHE = None

_TEXTO_DEFECTO = {
    "bienvenida": "Hola {nombre} {apellido}, ¡bienvenido/a a la empresa! Tu cuenta fue creada con éxito.",
    "desvinculacion": "Hola {nombre} {apellido}, te informamos que tu vínculo con la empresa ha finalizado. Gracias por tu paso por la organización.",
    "vacaciones_programadas": "Tus vacaciones fueron programadas desde {fechaInicio} hasta {fechaFin}. ¡Buen descanso!",
    "seguridad": "Para establecer o recuperar tu contraseña, usa este token (válido por {expiracion}): {token}.",
    "cuenta_desactivada_permanente": "Su cuenta fue desactivada en forma permanente. Motivo: {motivo}.",
    "cuenta_desactivada_temporal": "Su cuenta fue desactivada temporalmente. Motivo: {motivo}.",
    "cuenta_activada": "Su cuenta fue reactivada. ¡Bienvenido de regreso! Motivo: {motivo}.",
    "vacaciones_iniciadas": "Tus vacaciones comenzaron el {fechaInicio} y finalizan el {fechaFin}. ¡Buen descanso!",
    "vacaciones_finalizadas": "Tus vacaciones finalizaron: del {fechaInicio} al {fechaFin}. ¡Bienvenido/a de vuelta!",
}


def _plantilla(clave):
    """Texto de la plantilla (archivo o built-in) con {variables} sin rendir."""
    global _PLANTILLAS_CACHE
    if _PLANTILLAS_CACHE is None:
        ruta = os.environ.get("PLANTILLAS_PATH", _PLANTILLAS_PATH)
        try:
            with open(ruta, encoding="utf-8") as fh:
                _PLANTILLAS_CACHE = json.load(fh)
        except (OSError, ValueError):
            _PLANTILLAS_CACHE = {}
    return _PLANTILLAS_CACHE.get(clave) or _TEXTO_DEFECTO[clave]

logger = logging.getLogger("notificaciones")

EVENTO_CREADO = "empleado.creado"
EVENTO_RETIRADO = "empleado.retirado"
EVENTO_VACACIONES = "vacaciones.programadas"

# Reto 5: account lifecycle (auth-service) and scheduler transitions
# (vacaciones-service). Same data shapes as their original producers.
EVENTO_USUARIO_CREADO = "usuario.creado"
EVENTO_USUARIO_RECUPERACION = "usuario.recuperacion"
EVENTO_CUENTA_ACTIVADA = "cuenta.activada"
EVENTO_CUENTA_DESACTIVADA = "cuenta.desactivada"
EVENTO_VACACIONES_INICIADAS = "vacaciones.iniciadas"
EVENTO_VACACIONES_FINALIZADAS = "vacaciones.finalizadas"

TIPOS_VALIDOS = (
    EVENTO_CREADO,
    EVENTO_RETIRADO,
    EVENTO_VACACIONES,
    EVENTO_USUARIO_CREADO,
    EVENTO_USUARIO_RECUPERACION,
    EVENTO_CUENTA_ACTIVADA,
    EVENTO_CUENTA_DESACTIVADA,
    EVENTO_VACACIONES_INICIADAS,
    EVENTO_VACACIONES_FINALIZADAS,
)


class TipoEventoDesconocido(ValueError):
    """Raised when the envelope `type` is not one this service consumes."""


def construir_notificacion(evento: dict) -> Notificacion:
    """Map a catalog envelope to a Notificacion (not yet persisted)."""
    tipo_evento = evento.get("type")
    data = evento.get("data") or {}

    if tipo_evento == EVENTO_CREADO:
        nombre = data.get("nombre", "")
        apellido = data.get("apellido", "")
        return Notificacion(
            tipo="BIENVENIDA",
            destinatario=data["email"],
            mensaje=(
                _plantilla("bienvenida").format(nombre=nombre, apellido=apellido)
            ),
            empleado_id=data["id"],
        )

    if tipo_evento == EVENTO_RETIRADO:
        nombre = data.get("nombre", "")
        apellido = data.get("apellido", "")
        return Notificacion(
            tipo="DESVINCULACION",
            destinatario=data["email"],
            mensaje=(
                _plantilla("desvinculacion").format(nombre=nombre, apellido=apellido)
            ),
            empleado_id=data["id"],
        )

    if tipo_evento == EVENTO_VACACIONES:
        return Notificacion(
            tipo="VACACIONES",
            destinatario=data["empleadoEmail"],
            mensaje=(
                _plantilla("vacaciones_programadas").format(
                    fechaInicio=data["fechaInicio"], fechaFin=data["fechaFin"])
            ),
            empleado_id=data["empleadoId"],
        )

    if tipo_evento in (EVENTO_USUARIO_CREADO, EVENTO_USUARIO_RECUPERACION):
        # The reset token is a one-time JWT with short expiry; it is part of
        # the message the employee needs (PDF flow). No password is ever
        # present in these payloads, hence never logged.
        token = data["resetToken"]
        expiracion = data.get("expiracion", "30min")
        return Notificacion(
            tipo="SEGURIDAD",
            destinatario=data["email"],
            mensaje=(
                _plantilla("seguridad").format(token=token, expiracion=expiracion)
            ),
            empleado_id=data["empleadoId"],
        )

    if tipo_evento == EVENTO_CUENTA_DESACTIVADA:
        # permanente=True -> retiro; permanente=False -> suspensión temporal
        # (p. ej. inicio de vacaciones gestionado por auth-service).
        clave = (
            "cuenta_desactivada_permanente"
            if data.get("permanente", False)
            else "cuenta_desactivada_temporal"
        )
        return Notificacion(
            tipo="CUENTA",
            destinatario=data["email"],
            mensaje=(
                _plantilla(clave).format(motivo=data.get("motivo", "N/D"))
            ),
            empleado_id=data["empleadoId"],
        )

    if tipo_evento == EVENTO_CUENTA_ACTIVADA:
        return Notificacion(
            tipo="CUENTA",
            destinatario=data["email"],
            mensaje=(
                _plantilla("cuenta_activada").format(motivo=data.get("motivo", "N/D"))
            ),
            empleado_id=data["empleadoId"],
        )

    if tipo_evento == EVENTO_VACACIONES_INICIADAS:
        return Notificacion(
            tipo="VACACIONES",
            destinatario=data["empleadoEmail"],
            mensaje=(
                _plantilla("vacaciones_iniciadas").format(
                    fechaInicio=data["fechaInicio"], fechaFin=data["fechaFin"])
            ),
            empleado_id=data["empleadoId"],
        )

    if tipo_evento == EVENTO_VACACIONES_FINALIZADAS:
        return Notificacion(
            tipo="VACACIONES",
            destinatario=data["empleadoEmail"],
            mensaje=(
                _plantilla("vacaciones_finalizadas").format(
                    fechaInicio=data["fechaInicio"], fechaFin=data["fechaFin"])
            ),
            empleado_id=data["empleadoId"],
        )

    raise TipoEventoDesconocido(f"Tipo de evento no soportado: {tipo_evento!r}")


def log_envio(notificacion: Notificacion) -> None:
    """Structured log emitted for every simulated notification send."""
    logger.info(
        '[NOTIFICACIÓN] Tipo: %s | Para: %s | Mensaje: "%s"',
        notificacion.tipo,
        notificacion.destinatario,
        notificacion.mensaje,
    )
