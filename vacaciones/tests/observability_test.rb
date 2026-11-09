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

  # Los contadores son globales del proceso y otras pruebas también los
  # incrementan (el orden es aleatorio), así que se compara el incremento y no
  # el valor absoluto: antes fallaba según la semilla (p. ej. 10 en vez de 2).
  PETICIONES_GET = /http_requests_total\{[^}]*method="GET"[^}]*route="\/vacaciones"[^}]*code="200"[^}]*\} (\S+)/.freeze
  INICIADAS = /vacaciones_scheduler_transitions_total\{type="iniciadas"\} (\S+)/.freeze
  EVENTOS_INICIADAS = /eventos_publicados_total\{routing_key="vacaciones\.iniciadas"\} (\S+)/.freeze

  def test_metrics_text_expone_proceso_peticiones_y_contadores
    antes = Vacaciones::Observability.metrics_text

    Vacaciones::Observability.record_request('GET', '/vacaciones', '200', 0.012)
    Vacaciones::Observability.record_scheduler_transition('iniciadas', 2)
    Vacaciones::Observability.record_event_published('vacaciones.iniciadas')

    texto = Vacaciones::Observability.metrics_text

    assert_includes texto, 'process_cpu_seconds_total'
    assert_includes texto, 'process_resident_memory_bytes'
    assert_equal 1, valor(texto, PETICIONES_GET) - valor(antes, PETICIONES_GET)
    assert_equal 2, valor(texto, INICIADAS) - valor(antes, INICIADAS)
    assert_equal 1, valor(texto, EVENTOS_INICIADAS) - valor(antes, EVENTOS_INICIADAS)
  end

  # Valor numérico de la serie que casa con el patrón (0 si aún no existe).
  def valor(texto, patron)
    coincidencia = texto.match(patron)
    coincidencia ? coincidencia[1].to_f.round : 0
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
