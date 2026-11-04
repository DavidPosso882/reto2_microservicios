"""Plantillas configurables: override por archivo sin tocar código (T7)."""
import json

from app import mensajes


def test_plantilla_personalizada_sin_tocar_codigo(tmp_path, monkeypatch):
    override = tmp_path / "plantillas.json"
    override.write_text(json.dumps({"bienvenida": "Hola {nombre}, custom."}), encoding="utf-8")
    monkeypatch.setenv("PLANTILLAS_PATH", str(override))
    monkeypatch.setattr(mensajes, "_PLANTILLAS_CACHE", None)
    try:
        n = mensajes.construir_notificacion({
            "id": "x", "type": "empleado.creado", "version": "1.0",
            "occurredAt": "2026-11-04T00:00:00Z", "producer": "t",
            "data": {"id": "E1", "nombre": "Ada", "apellido": "L",
                     "email": "a@e.com"},
        })
        assert n.mensaje == "Hola Ada, custom."
    finally:
        monkeypatch.setattr(mensajes, "_PLANTILLAS_CACHE", None)


def test_plantilla_faltante_usa_builtin(tmp_path, monkeypatch):
    override = tmp_path / "plantillas.json"
    override.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("PLANTILLAS_PATH", str(override))
    monkeypatch.setattr(mensajes, "_PLANTILLAS_CACHE", None)
    try:
        n = mensajes.construir_notificacion({
            "id": "x", "type": "empleado.creado", "version": "1.0",
            "occurredAt": "2026-11-04T00:00:00Z", "producer": "t",
            "data": {"id": "E1", "nombre": "Ada", "apellido": "L",
                     "email": "a@e.com"},
        })
        assert "bienvenido/a a la empresa" in n.mensaje
    finally:
        monkeypatch.setattr(mensajes, "_PLANTILLAS_CACHE", None)
