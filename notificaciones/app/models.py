"""ORM models: processed-event dedup ledger and sent notifications."""

import uuid

from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Uuid as SaUuid

from app.db import Base


class EventoProcesado(Base):
    """Deduplication ledger keyed by the envelope `id` (see CATALOGO_EVENTOS.md §1)."""

    __tablename__ = "eventos_procesados"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    procesado_en: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Notificacion(Base):
    __tablename__ = "notificaciones"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    destinatario: Mapped[str] = mapped_column(String(255), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    fecha_envio: Mapped[str] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    empleado_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
