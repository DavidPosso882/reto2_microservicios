# frozen_string_literal: true

# La suite no debe exportar trazas a Zipkin (no hay collector en tests).
ENV['OTEL_SDK_DISABLED'] = 'true'

require 'json'
require 'minitest/autorun'
require 'time'

require_relative '../app/observability'

# Reto 8: contrato mínimo de observabilidad que no depende de las gemas
# externas (el entorno local no tiene bundler). Con gemas instaladas se usa
# prometheus-client/OpenTelemetry; sin ellas el fallback mantiene el mismo
# endpoint /metrics y el logging JSON.
class ObservabilityTest < Minitest::Test
  def setup
    Vacaciones::Observability.setup!
  end

  def test_metrics_text_expone_proceso_peticiones_y_contadores
    Vacaciones::Observability.record_request('GET', '/vacaciones', '200', 0.012)
    Vacaciones::Observability.record_scheduler_transition('iniciadas', 2)
    Vacaciones::Observability.record_event_published('vacaciones.iniciadas')

    texto = Vacaciones::Observability.metrics_text

    assert_includes texto, 'process_cpu_seconds_total'
    assert_includes texto, 'process_resident_memory_bytes'
    assert_match(/http_requests_total\{[^}]*method="GET"[^}]*route="\/vacaciones"[^}]*code="200"[^}]*\} 1/, texto)
    assert_includes texto, 'vacaciones_scheduler_transitions_total{type="iniciadas"} 2'
    assert_includes texto, 'eventos_publicados_total{routing_key="vacaciones.iniciadas"} 1'
  end

  def test_json_logger_incluye_campos_requeridos
    formatter = Vacaciones::Observability.json_logger_formatter
    linea = formatter.call('INFO', Time.utc(2026, 9, 28, 12, 0, 0), nil, 'hola')
    payload = JSON.parse(linea)

    assert_equal 'INFO', payload['level']
    assert_equal 'vacaciones-service', payload['service']
    assert_equal 'hola', payload['message']
    assert_equal '2026-09-28T12:00:00.000Z', payload['timestamp']
    assert payload.key?('traceId')
  end

  def test_tracer_fallback_ejecuta_el_bloque_y_devuelve_su_valor
    resultado = Vacaciones::Observability.tracer.in_span('vacaciones.test') do |span|
      span.set_attribute('k', 'v')
      :ok
    end

    assert_equal :ok, resultado
  end

  def test_inject_context_siempre_devuelve_un_hash
    headers = Vacaciones::Observability.inject_context({})

    assert_kind_of Hash, headers
  end
end
