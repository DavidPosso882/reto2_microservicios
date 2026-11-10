"""Observabilidad del servicio (Reto 8).

Expone /metrics en formato Prometheus, configura OpenTelemetry con exportador
Zipkin y propagación W3C (tracecontext + baggage), y estandariza los logs en
JSON con timestamp, level, service, traceId y message.

Las dependencias son opcionales en tiempo de import para que la suite local
sin `pip install` siga corriendo: si no están, el servicio degrada a no-op
(sin trazas) y /metrics usa un fallback de texto Prometheus.
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "notificaciones-service")
SERVICE_VERSION = "1.0.0"


def _zipkin_endpoint() -> str:
    raw = os.environ.get(
        "OTEL_EXPORTER_ZIPKIN_ENDPOINT", "http://zipkin:9411/api/v2/spans"
    )
    return raw if raw.endswith("/api/v2/spans") else f"{raw.rstrip('/')}/api/v2/spans"


ZIPKIN_ENDPOINT = _zipkin_endpoint()

try:  # OpenTelemetry API/SDK
    from opentelemetry import context, propagate, trace
    from opentelemetry.baggage.propagation import W3CBaggagePropagator
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import (
        ALWAYS_OFF,
        ALWAYS_ON,
        ParentBased,
        TraceIdRatioBased,
    )
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without deps
    OTEL_AVAILABLE = False

try:
    from opentelemetry.exporter.zipkin.json import ZipkinExporter
except ImportError:  # pragma: no cover
    ZipkinExporter = None

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
except ImportError:  # pragma: no cover
    FastAPIInstrumentor = None
    SQLAlchemyInstrumentor = None

try:
    from prometheus_client import generate_latest
    from prometheus_fastapi_instrumentator import Instrumentator

    INSTRUMENTATOR_AVAILABLE = True
except ImportError:  # pragma: no cover
    Instrumentator = None
    INSTRUMENTATOR_AVAILABLE = False

# Proyecto Final — métrica de negocio: notificaciones enviadas por tipo
# (BIENVENIDA, VACACIONES, CUENTA, SEGURIDAD, DESVINCULACION) y por evento
# de origen. Se registra en el registro por defecto de prometheus_client,
# que es el que publica /metrics.
try:
    from prometheus_client import Counter

    NOTIFICACIONES_ENVIADAS = Counter(
        "notificaciones_enviadas_total",
        "Notificaciones enviadas por tipo y evento de origen",
        ["tipo", "evento"],
    )
    # Series en 0 desde el arranque: sin esto la primera notificación de cada
    # tipo crea la serie ya en 1 y increase() de Prometheus no la cuenta.
    for _evento, _tipo in (
        ("empleado.creado", "BIENVENIDA"),
        ("empleado.retirado", "DESVINCULACION"),
        ("vacaciones.programadas", "VACACIONES"),
        ("vacaciones.iniciadas", "VACACIONES"),
        ("vacaciones.finalizadas", "VACACIONES"),
        ("usuario.creado", "SEGURIDAD"),
        ("usuario.recuperacion", "SEGURIDAD"),
        ("cuenta.activada", "CUENTA"),
        ("cuenta.desactivada", "CUENTA"),
    ):
        NOTIFICACIONES_ENVIADAS.labels(tipo=_tipo, evento=_evento)
except ImportError:  # pragma: no cover
    NOTIFICACIONES_ENVIADAS = None


def record_notificacion_enviada(tipo: str, evento: str) -> None:
    """Cuenta una notificación enviada; no-op si prometheus_client no está."""
    if NOTIFICACIONES_ENVIADAS is not None:
        NOTIFICACIONES_ENVIADAS.labels(tipo=tipo or "?", evento=evento or "?").inc()

_tracing_configured = False
_logging_configured = False

# Los reset tokens del flujo de recuperación son JWT: nunca deben aparecer en
# la línea de log (el mensaje persistido/enviado sí los conserva).
_TOKEN_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


# ── Logs JSON ────────────────────────────────────────────────────────────────
class JsonFormatter(logging.Formatter):
    """Formatea cada registro como una línea JSON del contrato Reto 8."""

    def format(self, record: logging.LogRecord) -> str:
        message = _TOKEN_RE.sub("[REDACTED]", record.getMessage())
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "traceId": current_trace_id(),
            "message": message,
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = _TOKEN_RE.sub(
                "[REDACTED]", self.formatException(record.exc_info)
            )
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """Instala el formatter JSON una sola vez (idempotente para tests)."""
    global _logging_configured
    if _logging_configured:
        return
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    _logging_configured = True


# ── OpenTelemetry ────────────────────────────────────────────────────────────
def _sdk_disabled() -> bool:
    return os.environ.get("OTEL_SDK_DISABLED", "false").lower() == "true"


def _sampler():
    name = os.environ.get("OTEL_TRACES_SAMPLER", "parentbased_always_on")
    if name == "always_off":
        return ALWAYS_OFF
    if name == "traceidratio":
        try:
            ratio = float(os.environ.get("OTEL_TRACES_SAMPLER_ARG", "1"))
        except ValueError:
            ratio = 1.0
        return TraceIdRatioBased(max(0.0, min(1.0, ratio)))
    return ParentBased(ALWAYS_ON)


def setup_tracing(app, engine) -> None:
    """Configura el provider global, el exportador Zipkin y la instrumentación."""
    global _tracing_configured
    if not OTEL_AVAILABLE or _sdk_disabled():
        return

    if not _tracing_configured:
        resource = Resource.create(
            {"service.name": SERVICE_NAME, "service.version": SERVICE_VERSION}
        )
        provider = TracerProvider(resource=resource, sampler=_sampler())
        if ZipkinExporter is not None:
            provider.add_span_processor(
                BatchSpanProcessor(ZipkinExporter(endpoint=ZIPKIN_ENDPOINT))
            )
        trace.set_tracer_provider(provider)
        propagate.set_global_textmap(
            CompositePropagator(
                [TraceContextTextMapPropagator(), W3CBaggagePropagator()]
            )
        )
        _tracing_configured = True

    if FastAPIInstrumentor is not None:
        FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/metrics")
    if SQLAlchemyInstrumentor is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine)


def tracer():
    """Devuelve el tracer del servicio o un no-op si OTel no está instalado."""
    if OTEL_AVAILABLE:
        return trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)
    return _NullTracer()


def current_trace_id() -> str | None:
    if not OTEL_AVAILABLE:
        return None
    span_context = trace.get_current_span().get_span_context()
    if not span_context or not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


@contextmanager
def extracted_context(headers):
    """Adjunta el contexto W3C recibido en las cabeceras AMQP.

    Los consumidores lo usan para que el span de procesamiento sea hijo del
    span raíz del scheduler/productor (una sola cascada distribuida).
    """
    if not OTEL_AVAILABLE:
        yield None
        return
    ctx = propagate.extract(carrier=headers or {})
    token = context.attach(ctx)
    try:
        yield ctx
    finally:
        context.detach(token)


class _NullSpan:
    def set_attribute(self, *_args, **_kwargs) -> None:
        return None

    def record_exception(self, *_args, **_kwargs) -> None:
        return None


@contextmanager
def _null_span():
    yield _NullSpan()


class _NullTracer:
    def start_as_current_span(self, _name, context=None, attributes=None, **_kwargs):
        return _null_span()


# ── Métricas Prometheus ──────────────────────────────────────────────────────
def setup_metrics(app) -> None:
    """Instrumenta FastAPI y expone /metrics (prometheus-fastapi-instrumentator)."""
    if INSTRUMENTATOR_AVAILABLE:
        Instrumentator().instrument(app).expose(
            app, endpoint="/metrics", include_in_schema=False
        )
        return

    # Fallback mínimo si la librería no está instalada (entorno local).
    from fastapi.responses import PlainTextResponse

    @app.get("/metrics", include_in_schema=False)
    def metrics_fallback():
        return PlainTextResponse(_fallback_metrics(), media_type="text/plain; version=0.0.4")


def _fallback_metrics() -> str:
    try:
        return generate_latest().decode("utf-8")
    except Exception:
        return (
            "# HELP process_cpu_seconds_total Tiempo de CPU del proceso en segundos\n"
            "# TYPE process_cpu_seconds_total gauge\n"
            "process_cpu_seconds_total 0\n"
        )
