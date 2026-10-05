"""Pytest fixtures: SQLite test DB, no RabbitMQ and no real Postgres needed."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CONSUMER_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import crear_app
from app.models import Notificacion
from app.mensajes import construir_notificacion


@pytest.fixture()
def sesion():
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def cliente(sesion):
    # Los tests usan el mismo objeto que producción (sin root_path): el gateway
    # es el único que agrega/quita prefijos, TestClient no pasa por él.
    app = crear_app()
    # The dependency must use the SAME engine (SQLite in-memory, StaticPool).
    app.dependency_overrides[obtener_sesion_original()] = lambda: sesion
    with TestClient(app) as c:
        yield c


def obtener_sesion_original():
    from app.db import get_session

    return get_session


def evento_envelope(tipo: str, data: dict, evento_id: str = "evt-1") -> dict:
    return {
        "id": evento_id,
        "type": tipo,
        "version": "1.0",
        "occurredAt": "2026-09-21T14:30:00Z",
        "producer": "empleados-service",
        "data": data,
    }


DATA_CREADO = {
    "id": "E001",
    "nombre": "Juan",
    "apellido": "Pérez",
    "email": "juan.perez@empresa.com",
    "numeroEmpleado": "EMP-2026-001",
    "cargo": "Desarrollador Senior",
    "area": "Tecnología",
    "departamentoId": "IT",
    "fechaIngreso": "2026-03-01",
    "estado": "ACTIVO",
}

DATA_RETIRADO = {
    "id": "E001",
    "nombre": "Juan",
    "apellido": "Pérez",
    "email": "juan.perez@empresa.com",
    "estado": "RETIRADO",
    "fechaRetiro": "2026-09-21T14:30:00Z",
}

DATA_VACACIONES = {
    "id": "V-2026-0042",
    "empleadoId": "E001",
    "empleadoEmail": "juan.perez@empresa.com",
    "fechaInicio": "2026-12-15",
    "fechaFin": "2026-12-30",
    "estado": "PROGRAMADA",
    "fechaCreacion": "2026-09-21T14:30:00Z",
}


def persistir(sesion, tipo: str, data: dict, evento_id: str = "evt-1") -> Notificacion:
    """Apply an envelope through the real pipeline (dedup + mapping)."""
    from app.consumer import procesar_evento

    procesar_evento(sesion, evento_envelope(tipo, data, evento_id))
    sesion.expire_all()
    filas = sesion.query(Notificacion).all()
    assert filas, "la notificación no fue persistida"
    return filas[-1]
