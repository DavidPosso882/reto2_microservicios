"""Read-only endpoint tests: camelCase keys, filtering, 404-free semantics."""

from tests.conftest import persistir


def test_listar_vacio(cliente):
    resp = cliente.get("/notificaciones")
    assert resp.status_code == 200
    assert resp.json() == []


def test_listar_todas(cliente, sesion):
    persistir(sesion, "empleado.creado", {
        "id": "E001", "nombre": "Juan", "apellido": "Pérez",
        "email": "juan.perez@empresa.com",
    }, "evt-1")

    resp = cliente.get("/notificaciones")
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert len(cuerpo) == 1
    assert set(cuerpo[0].keys()) == {
        "id", "tipo", "destinatario", "mensaje", "fechaEnvio", "empleadoId",
    }
    assert cuerpo[0]["tipo"] == "BIENVENIDA"
    assert cuerpo[0]["empleadoId"] == "E001"


def test_filtrar_por_empleado(cliente, sesion):
    persistir(sesion, "empleado.creado", {
        "id": "E001", "nombre": "Juan", "apellido": "Pérez",
        "email": "juan.perez@empresa.com",
    }, "evt-1")
    persistir(sesion, "vacaciones.programadas", {
        "id": "V-2026-0042", "empleadoId": "E002",
        "empleadoEmail": "maria.gomez@empresa.com",
        "fechaInicio": "2026-12-15", "fechaFin": "2026-12-30",
    }, "evt-2")

    resp = cliente.get("/notificaciones/E001")
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert len(cuerpo) == 1
    assert cuerpo[0]["empleadoId"] == "E001"
    assert cuerpo[0]["tipo"] == "BIENVENIDA"

    # Unknown employee: empty list, not an error (read-only, pure query).
    resp = cliente.get("/notificaciones/NO-EXISTE")
    assert resp.status_code == 200
    assert resp.json() == []


def test_health_expone_status_y_checks(cliente):
    resp = cliente.get("/health")
    assert resp.status_code == 200
    cuerpo = resp.json()
    assert cuerpo["status"] == "UP"
    assert cuerpo["service"] == "notificaciones-service"
    assert set(cuerpo["checks"]) == {"database", "messageBroker"}


def test_metrics_expone_formato_prometheus(cliente):
    cliente.get("/notificaciones")
    resp = cliente.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
    assert "http_request_duration_seconds" in resp.text


def test_serializacion_camel_case_con_valores(cliente, sesion):
    n = persistir(sesion, "vacaciones.programadas", {
        "id": "V-2026-0042", "empleadoId": "E001",
        "empleadoEmail": "juan.perez@empresa.com",
        "fechaInicio": "2026-12-15", "fechaFin": "2026-12-30",
    }, "evt-3")

    resp = cliente.get("/notificaciones/E001")
    cuerpo = resp.json()[0]
    assert cuerpo["id"] == str(n.id)
    assert "fechaEnvio" in cuerpo and "empleadoId" in cuerpo
    assert "fecha_envio" not in cuerpo and "empleado_id" not in cuerpo
    assert cuerpo["fechaEnvio"] is not None
