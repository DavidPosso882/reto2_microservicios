"""Event -> notification mapping (CATALOGO_EVENTOS.md sections 3.1, 3.3, 3.8)."""

import logging

from app.models import Notificacion

logger = logging.getLogger("notificaciones")

EVENTO_CREADO = "empleado.creado"
EVENTO_RETIRADO = "empleado.retirado"
EVENTO_VACACIONES = "vacaciones.programadas"

TIPOS_VALIDOS = (EVENTO_CREADO, EVENTO_RETIRADO, EVENTO_VACACIONES)


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
                f"Hola {nombre} {apellido}, ¡bienvenido/a a la empresa! "
                "Tu cuenta fue creada con éxito."
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
                f"Hola {nombre} {apellido}, te informamos que tu vínculo con la "
                "empresa ha finalizado. Gracias por tu paso por la organización."
            ),
            empleado_id=data["id"],
        )

    if tipo_evento == EVENTO_VACACIONES:
        return Notificacion(
            tipo="VACACIONES",
            destinatario=data["empleadoEmail"],
            mensaje=(
                "Tus vacaciones fueron programadas desde "
                f"{data['fechaInicio']} hasta {data['fechaFin']}. ¡Buen descanso!"
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
