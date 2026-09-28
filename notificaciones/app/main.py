"""HTTP layer: read-only REST endpoints with camelCase JSON (Reto contract)."""

import os
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.consumer import detener_consumer, iniciar_consumer
from app.db import Base, engine, get_session
from app.models import Notificacion
from app.mensajes import log_envio  # re-exported for tests


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def serializar(notificacion: Notificacion) -> dict:
    """camelCase serialization as required by the course contract."""
    empleado_id = notificacion.empleado_id
    if isinstance(empleado_id, uuid.UUID):
        empleado_id = str(empleado_id)
    return {
        "id": str(notificacion.id),
        "tipo": notificacion.tipo,
        "destinatario": notificacion.destinatario,
        "mensaje": notificacion.mensaje,
        "fechaEnvio": _iso(notificacion.fecha_envio),
        "empleadoId": empleado_id,
    }


def crear_app(root_path: str | None = None) -> FastAPI:
    # root_path inyectable solo para tests (TestClient no pasa por el gateway:
    # su scope hereda app.root_path y el strip del gateway lo dejaria en "").
    # Produccion mantiene /notificaciones (env NOTIFICACIONES_ROOT_PATH).
    effective = root_path if root_path is not None else os.getenv(
        "NOTIFICACIONES_ROOT_PATH", "/notificaciones"
    )
    app = FastAPI(
        title="notificaciones-service",
        description=(
            "Servicio puramente reactivo del ecosistema: consume eventos de "
            "RabbitMQ, simula el envío de notificaciones y expone su historial "
            "solo en lectura (Reto 4). Vía gateway en /notificaciones/docs."
        ),
        version="1.0.0",
        # Gateway sirve docs con strip (/notificaciones/docs -> /docs upstream).
        # root_path hace que /docs fetchee /notificaciones/openapi.json,
        # que el gateway vuelve a stripear a /openapi.json. Sin esto el UI
        # pediría /openapi.json pelado y el gateway no sabría a qué servicio va.
        root_path=effective,
    )

    @app.on_event("startup")
    def _startup() -> None:
        # Single schema-creation path: SQLAlchemy (see service README).
        Base.metadata.create_all(bind=engine)
        # Reactive half of the service: consume ecosystem events in a daemon
        # thread unless the consumer is disabled via env (CONSUMER_ENABLED).
        if settings.consumer_enabled:
            iniciar_consumer()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        # Clean stop: cancel consumption and close the AMQP connection.
        if settings.consumer_enabled:
            detener_consumer()

    @app.get("/notificaciones")
    def listar_notificaciones(session: Session = Depends(get_session)):
        rows = session.execute(
            select(Notificacion).order_by(Notificacion.fecha_envio)
        ).scalars().all()
        return [serializar(n) for n in rows]

    @app.get("/notificaciones/{empleado_id}")
    def notificaciones_por_empleado(
        empleado_id: str, session: Session = Depends(get_session)
    ):
        rows = session.execute(
            select(Notificacion)
            .where(Notificacion.empleado_id == empleado_id)
            .order_by(Notificacion.fecha_envio)
        ).scalars().all()
        return [serializar(n) for n in rows]

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "notificaciones-service"}

    return app


app = crear_app()
