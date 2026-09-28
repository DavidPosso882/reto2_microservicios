"""Reto 5: nuevos eventos consumidos (ciclo de vida de cuenta + scheduler).

Cubre:
  - Mapping de los 6 routing keys nuevos -> tipos SEGURIDAD / CUENTA / VACACIONES.
  - Formato de log del PDF: [NOTIFICACIÓN] Tipo: X | Para: Y | Mensaje: "...".
    El token de reset sí se registra (así lo pide el flujo del PDF); la
    contraseña JAMÁS aparece en el log (nunca entra a los payloads).
  - QUEUE todavía desconoce empleados con `id` y `empleadoId` mezclados.
  - ROUTING_KEYS del consumer: las 3 originales intactas + las 6 nuevas,
    y la topología declara exactamente esos 9 bindings.
  - Dedup aplicado igual a los eventos nuevos.
  - Payloads incompletos de los nuevos tipos siguen siendo `poison`
    (se descartan con ACK, no bloquean la cola).
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import select

import app.consumer as consumer_module
from app.consumer import Consumer, MensajeEnvenenado, procesar_evento
from app.mensajes import construir_notificacion, log_envio
from app.models import EventoProcesado, Notificacion

from tests.conftest import DATA_VACACIONES, evento_envelope


DATA_USUARIO_CREADO = {
    "empleadoId": "E001",
    "email": "juan.perez@empresa.com",
    "nombre": "Juan",
    "apellido": "Pérez",
    "resetToken": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJFMDAxIn0.token-demo",
}

DATA_USUARIO_RECUPERACION = {
    "email": "juan.perez@empresa.com",
    "empleadoId": "E001",
    "resetToken": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJFMDAxIn0.token-demo",
    "expiracion": "30min",
}

DATA_CUENTA_DESACTIVADA = {
    "email": "juan.perez@empresa.com",
    "empleadoId": "E001",
    "motivo": "RETIRO",
    "permanente": True,
}

DATA_CUENTA_ACTIVADA = {
    "email": "juan.perez@empresa.com",
    "empleadoId": "E001",
    "motivo": "FIN_VACACIONES",
}


DATA_NUEVOS_TIPOS = (
    ("usuario.creado", DATA_USUARIO_CREADO),
    ("usuario.recuperacion", DATA_USUARIO_RECUPERACION),
    ("cuenta.desactivada", DATA_CUENTA_DESACTIVADA),
    ("cuenta.activada", DATA_CUENTA_ACTIVADA),
    ("vacaciones.iniciadas", DATA_VACACIONES),
    ("vacaciones.finalizadas", DATA_VACACIONES),
)


# -- mapping de los 6 nuevos eventos ------------------------------------------


def test_usuario_creado_genera_seguridad_con_token():
    n = construir_notificacion(evento_envelope("usuario.creado", DATA_USUARIO_CREADO))
    assert n.tipo == "SEGURIDAD"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "Para establecer o recuperar" in n.mensaje
    assert DATA_USUARIO_CREADO["resetToken"] in n.mensaje


def test_usuario_recuperacion_genera_seguridad_con_expiracion():
    n = construir_notificacion(
        evento_envelope("usuario.recuperacion", DATA_USUARIO_RECUPERACION)
    )
    assert n.tipo == "SEGURIDAD"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "Para establecer o recuperar" in n.mensaje
    assert DATA_USUARIO_RECUPERACION["resetToken"] in n.mensaje
    assert "30min" in n.mensaje


def test_cuenta_desactivada_genera_cuenta():
    n = construir_notificacion(
        evento_envelope("cuenta.desactivada", DATA_CUENTA_DESACTIVADA)
    )
    assert n.tipo == "CUENTA"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert n.mensaje.startswith("Su cuenta fue desactivada")
    assert "RETIRO" in n.mensaje


def test_cuenta_activada_genera_cuenta_bienvenido_de_regreso():
    n = construir_notificacion(
        evento_envelope("cuenta.activada", DATA_CUENTA_ACTIVADA)
    )
    assert n.tipo == "CUENTA"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "Bienvenido de regreso" in n.mensaje


def test_vacaciones_iniciadas_genera_vacaciones():
    n = construir_notificacion(evento_envelope("vacaciones.iniciadas", DATA_VACACIONES))
    assert n.tipo == "VACACIONES"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "2026-12-15" in n.mensaje and "2026-12-30" in n.mensaje
    assert "comenz" in n.mensaje.lower()


def test_vacaciones_finalizadas_genera_vacaciones():
    n = construir_notificacion(
        evento_envelope("vacaciones.finalizadas", DATA_VACACIONES)
    )
    assert n.tipo == "VACACIONES"
    assert n.destinatario == "juan.perez@empresa.com"
    assert n.empleado_id == "E001"
    assert "2026-12-15" in n.mensaje and "2026-12-30" in n.mensaje
    assert "finaliz" in n.mensaje.lower()


# -- formato de log del PDF (y seguridad del log) ------------------------------


def test_log_formato_pdf_seguridad(caplog):
    n = construir_notificacion(evento_envelope("usuario.recuperacion", DATA_USUARIO_RECUPERACION))
    with caplog.at_level("INFO", logger="notificaciones"):
        log_envio(n)
    esperado = (
        f'[NOTIFICACIÓN] Tipo: SEGURIDAD | Para: juan.perez@empresa.com '
        f'| Mensaje: "{n.mensaje}"'
    )
    assert esperado in caplog.messages


def test_log_seguridad_no_registra_password(caplog):
    """La contraseña nunca debe aparecer en el log (el payload no la trae)."""
    n = construir_notificacion(evento_envelope("usuario.creado", DATA_USUARIO_CREADO))
    with caplog.at_level("INFO", logger="notificaciones"):
        log_envio(n)
    assert all("password" not in m.lower() for m in caplog.messages)


# -- routing keys del consumer (3 originales + 6 nuevas) ------------------------


def test_routing_keys_conserva_las_3_y_agrega_las_6_nuevas():
    claves = consumer_module.ROUTING_KEYS
    assert claves[:3] == ("empleado.creado", "empleado.retirado", "vacaciones.programadas")
    for clave in (
        "usuario.creado",
        "usuario.recuperacion",
        "cuenta.activada",
        "cuenta.desactivada",
        "vacaciones.iniciadas",
        "vacaciones.finalizadas",
    ):
        assert clave in claves
    assert len(claves) == 9
    assert len(set(claves)) == 9


def test_topologia_declara_los_9_bindings_en_orden():
    consumer = Consumer("localhost", 5672, "guest", "guest")
    channel = Mock()
    consumer._configurar_topologia(channel)
    claves = [c.kwargs["routing_key"] for c in channel.queue_bind.call_args_list]
    assert claves == list(consumer_module.ROUTING_KEYS)
    assert all(
        c.kwargs["exchange"] == consumer_module.EXCHANGE
        and c.kwargs["queue"] == consumer_module.QUEUE
        for c in channel.queue_bind.call_args_list
    )


# -- dedup se aplica igual a los eventos nuevos ---------------------------------


@pytest.mark.parametrize("tipo,data", list(DATA_NUEVOS_TIPOS))
@pytest.mark.usefixtures("sesion")
def test_dedup_nuevos_tipos(sesion, tipo, data):
    """Segundo `id` idéntico -> False y una sola notificación por tipo."""
    env = evento_envelope(tipo, data, evento_id=f"evt-dedup-{tipo}")
    assert procesar_evento(sesion, env) is True
    assert procesar_evento(sesion, env) is False
    filas = (
        sesion.execute(select(Notificacion)).scalars().all()
    )
    assert len(filas) == 1
    assert sesion.query(EventoProcesado).count() == 1


# -- payload incompleto de los nuevos tipos sigue siendo poison ------------------


def _sin(data: dict, clave: str) -> dict:
    return {k: v for k, v in data.items() if k != clave}


@pytest.mark.parametrize(
    "tipo,data",
    [
        ("usuario.creado", _sin(DATA_USUARIO_CREADO, "resetToken")),
        ("usuario.creado", _sin(DATA_USUARIO_CREADO, "email")),
        ("usuario.recuperacion", _sin(DATA_USUARIO_RECUPERACION, "resetToken")),
        ("cuenta.desactivada", _sin(DATA_CUENTA_DESACTIVADA, "email")),
        ("cuenta.activada", _sin(DATA_CUENTA_ACTIVADA, "email")),
        ("vacaciones.iniciadas", _sin(DATA_VACACIONES, "empleadoEmail")),
        ("vacaciones.finalizadas", _sin(DATA_VACACIONES, "fechaFin")),
    ],
)
def test_data_incompleta_nuevos_tipos_es_poison(sesion, tipo, data):
    env = evento_envelope(tipo, data, "evt-poison-nuevo")
    with pytest.raises(MensajeEnvenenado):
        procesar_evento(sesion, env)
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0


# --lado AMQP: poison de los nuevos descartado con ACK (no reencola) -------------


def _metodo_amqp(delivery_tag: int = 1, routing_key: str = "usuario.creado"):
    return SimpleNamespace(delivery_tag=delivery_tag, routing_key=routing_key)


def _cuerpo(envelope: dict) -> bytes:
    import json

    return json.dumps(envelope).encode("utf-8")


def test_tipo_nuevo_incompleto_se_descarta_con_ack(sesion):
    env = evento_envelope("usuario.creado", _sin(DATA_USUARIO_CREADO, "resetToken"))
    canal = Mock()
    Consumer("localhost", 5672, "guest", "guest")._on_message(
        canal, _metodo_amqp(), None, _cuerpo(env)
    )
    canal.basic_ack.assert_called_once_with(delivery_tag=1)
    canal.basic_nack.assert_not_called()
    assert sesion.query(Notificacion).count() == 0
    assert sesion.query(EventoProcesado).count() == 0
