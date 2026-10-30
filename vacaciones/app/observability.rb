# frozen_string_literal: true

require 'json'
require 'time'

module Vacaciones
  # Observabilidad del servicio (Reto 8):
  #   - Métricas Prometheus (prometheus-client si está disponible; fallback
  #     de texto con la misma semántica para que la suite local sin gemas
  #     siga corriendo).
  #   - OpenTelemetry con exportador Zipkin y propagación W3C
  #     tracecontext + baggage. Si las gemas no están instaladas, el módulo
  #     degrada a no-op (la app sigue funcionando).
  #   - Utilidades de logging JSON (timestamp, level, service, traceId, message).
  #
  # El scheduler usa `tracer.in_span` como span raíz manual y `inject_context`
  # propaga traceparent/baggage en las cabeceras AMQP; auth-service y
  # notificaciones extraen ese contexto para continuar una única cascada.
  module Observability
    SERVICE_NAME = ENV.fetch('OTEL_SERVICE_NAME', 'vacaciones-service')
    SERVICE_VERSION = '1.0.0'
    DEFAULT_ZIPKIN_ENDPOINT = 'http://zipkin:9411/api/v2/spans'
    METRICS_CONTENT_TYPE = 'text/plain; version=0.0.4; charset=utf-8'

    PROMETHEUS_AVAILABLE = begin
      require 'prometheus/client'
      require 'prometheus/client/formats/text'
      true
    rescue LoadError
      false
    end

    OTEL_AVAILABLE = begin
      require 'opentelemetry/sdk'
      require 'opentelemetry/exporter/zipkin'
      require 'opentelemetry/instrumentation/rack'
      require 'opentelemetry/instrumentation/sinatra'
      require 'opentelemetry/instrumentation/bunny'
      true
    rescue LoadError
      false
    end

    # Span/tracer mínimos para que el código de negocio no dependa de la
    # presencia de las gemas de OpenTelemetry.
    class NullSpan
      def set_attribute(_key, _value); end

      def record_exception(_error); end

      def status=(_value); end
    end

    class NullTracer
      def in_span(_name, attributes: {}, **_options)
        yield NullSpan.new
      end
    end

    @metrics_configured = false
    @tracing_configured = false
    @request_counts = Hash.new(0)
    @request_durations = Hash.new { |hash, key| hash[key] = { count: 0, sum: 0.0 } }
    @scheduler_counts = Hash.new(0)
    @event_counts = Hash.new(0)
    @mutex = Mutex.new

    class << self
      attr_reader :registry, :http_requests, :http_duration

      def setup!
        setup_metrics
        setup_tracing
      end

      # ── Métricas Prometheus ────────────────────────────────────────────────
      def setup_metrics
        return if @metrics_configured

        @metrics_configured = true
        return unless PROMETHEUS_AVAILABLE

        @registry = Prometheus::Client::Registry.new
        @http_requests = @registry.counter(
          :http_requests_total,
          docstring: 'Total de peticiones HTTP por metodo, ruta y codigo',
          labels: %i[method route code]
        )
        @http_duration = @registry.histogram(
          :http_request_duration_seconds,
          docstring: 'Duracion de peticiones HTTP en segundos',
          labels: %i[method route code],
          buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
        )
        @process_cpu = @registry.gauge(
          :process_cpu_seconds_total,
          docstring: 'Tiempo de CPU del proceso en segundos'
        )
        @process_memory = @registry.gauge(
          :process_resident_memory_bytes,
          docstring: 'Memoria residente del proceso en bytes'
        )
        @scheduler_transitions = @registry.counter(
          :vacaciones_scheduler_transitions_total,
          docstring: 'Transiciones aplicadas por el scheduler',
          labels: %i[type]
        )
        @events_published = @registry.counter(
          :eventos_publicados_total,
          docstring: 'Eventos publicados al message broker',
          labels: %i[routing_key]
        )
      end

      def record_request(method, route, code, duration_s)
        setup_metrics
        @mutex.synchronize do
          key = [method.to_s, route.to_s, code.to_s]
          @request_counts[key] += 1
          bucket = @request_durations[key]
          bucket[:count] += 1
          bucket[:sum] += duration_s.to_f
        end
        return unless PROMETHEUS_AVAILABLE

        labels = { method: method.to_s, route: route.to_s, code: code.to_s }
        @http_requests&.increment(labels: labels)
        @http_duration&.observe(duration_s.to_f, labels: labels)
      rescue StandardError
        nil
      end

      def record_scheduler_transition(type, count = 1)
        setup_metrics
        amount = count.to_i
        return if amount <= 0

        @mutex.synchronize { @scheduler_counts[type.to_s] += amount }
        @scheduler_transitions&.increment(by: amount, labels: { type: type.to_s })
      rescue StandardError
        nil
      end

      def record_event_published(routing_key)
        setup_metrics
        @mutex.synchronize { @event_counts[routing_key.to_s] += 1 }
        @events_published&.increment(labels: { routing_key: routing_key.to_s })
      rescue StandardError
        nil
      end

      def metrics_text
        setup_metrics
        if PROMETHEUS_AVAILABLE
          update_process_metrics
          Prometheus::Client::Formats::Text.marshal(@registry)
        else
          fallback_metrics_text
        end
      end

      # ── OpenTelemetry ─────────────────────────────────────────────────────
      def setup_tracing
        return if @tracing_configured

        @tracing_configured = true
        return unless OTEL_AVAILABLE
        return if ENV['OTEL_SDK_DISABLED'].to_s.downcase == 'true'

        exporter = build_zipkin_exporter
        processor = OpenTelemetry::SDK::Trace::Export::BatchSpanProcessor.new(exporter)

        OpenTelemetry::SDK.configure do |config|
          config.service_name = SERVICE_NAME
          config.service_version = SERVICE_VERSION
          config.add_span_processor(processor)
          config.propagators = [
            OpenTelemetry::Trace::Propagation::TraceContext::TextMapPropagator.new,
            OpenTelemetry::Baggage::Propagation::TextMapPropagator.new
          ]
          config.use 'OpenTelemetry::Instrumentation::Rack'
          config.use 'OpenTelemetry::Instrumentation::Sinatra'
          config.use 'OpenTelemetry::Instrumentation::Bunny'
        end
      rescue StandardError => e
        warn "[vacaciones-service] tracing no configurado: #{e.class}: #{e.message}"
      end

      def tracer
        @tracer ||= if OTEL_AVAILABLE
                      OpenTelemetry.tracer_provider.tracer(SERVICE_NAME, SERVICE_VERSION)
                    else
                      NullTracer.new
                    end
      end

      # Inyecta traceparent/tracestate/baggage en un hash de cabeceras AMQP.
      def inject_context(headers = {})
        return headers unless OTEL_AVAILABLE

        OpenTelemetry.propagation.inject(headers)
        headers
      rescue StandardError
        headers
      end

      def extract_context(headers)
        return {} unless OTEL_AVAILABLE

        OpenTelemetry.propagation.extract(headers || {})
      rescue StandardError
        OpenTelemetry::Context.current
      end

      # Ejecuta el bloque con el contexto extraído del mensaje (continuidad
      # de la traza). Sin OTel, ejecuta el bloque tal cual.
      def with_context(headers)
        return yield unless OTEL_AVAILABLE

        OpenTelemetry::Context.with_current(extract_context(headers)) { yield }
      end

      def trace_id
        return nil unless OTEL_AVAILABLE

        span_context = OpenTelemetry::Trace.current_span.context
        return nil unless span_context.valid?

        format('%032x', span_context.trace_id)
      rescue StandardError
        nil
      end

      def json_logger_formatter
        proc do |severity, time, _progname, message|
          payload = {
            timestamp: time.utc.iso8601(3),
            level: severity,
            service: SERVICE_NAME,
            traceId: trace_id,
            message: message.is_a?(String) ? message : message.inspect
          }
          "#{JSON.generate(payload)}\n"
        end
      end

      private

      # El exporter Ruby agrega /api/v2/spans cuando endpoint == ENV. Se
      # normaliza la variable a la URL base para aceptar tanto la base como la
      # URL completa (contrato del reto: http://zipkin:9411/api/v2/spans).
      def build_zipkin_exporter
        previous = ENV['OTEL_EXPORTER_ZIPKIN_ENDPOINT']
        base = (previous.nil? || previous.empty? ? DEFAULT_ZIPKIN_ENDPOINT : previous)
               .sub(%r{/api/v2/spans\z}, '')
               .sub(%r{/+\z}, '')
        base = 'http://zipkin:9411' if base.empty?
        ENV['OTEL_EXPORTER_ZIPKIN_ENDPOINT'] = base
        OpenTelemetry::Exporter::Zipkin::Exporter.new
      ensure
        if previous.nil?
          ENV.delete('OTEL_EXPORTER_ZIPKIN_ENDPOINT')
        else
          ENV['OTEL_EXPORTER_ZIPKIN_ENDPOINT'] = previous
        end
      end

      def update_process_metrics
        @process_cpu&.set(Process.clock_gettime(Process::CLOCK_PROCESS_CPUTIME_ID))
        @process_memory&.set(resident_memory_bytes)
      rescue StandardError
        nil
      end

      def resident_memory_bytes
        status = File.read('/proc/self/status')
        kilobytes = status[/^VmRSS:\s+(\d+)\s+kB/, 1].to_i
        kilobytes * 1024
      rescue StandardError
        0
      end

      def fallback_metrics_text
        lines = []
        lines << '# HELP process_cpu_seconds_total Tiempo de CPU del proceso en segundos'
        lines << '# TYPE process_cpu_seconds_total gauge'
        lines << format('process_cpu_seconds_total %.6f',
                        Process.clock_gettime(Process::CLOCK_PROCESS_CPUTIME_ID))
        lines << '# HELP process_resident_memory_bytes Memoria residente del proceso en bytes'
        lines << '# TYPE process_resident_memory_bytes gauge'
        lines << "process_resident_memory_bytes #{resident_memory_bytes}"
        lines << '# HELP http_requests_total Total de peticiones HTTP'
        lines << '# TYPE http_requests_total counter'
        @request_counts.each do |(method, route, code), count|
          lines << "http_requests_total#{fallback_labels(method, route, code)} #{count}"
        end
        lines << '# HELP http_request_duration_seconds Duracion de peticiones HTTP'
        lines << '# TYPE http_request_duration_seconds summary'
        @request_durations.each do |(method, route, code), bucket|
          labels = fallback_labels(method, route, code)
          lines << "http_request_duration_seconds_sum#{labels} #{format('%.6f', bucket[:sum])}"
          lines << "http_request_duration_seconds_count#{labels} #{bucket[:count]}"
        end
        lines << '# HELP vacaciones_scheduler_transitions_total Transiciones del scheduler'
        lines << '# TYPE vacaciones_scheduler_transitions_total counter'
        @scheduler_counts.each do |type, count|
          lines << %(vacaciones_scheduler_transitions_total{type="#{escape_label(type)}"} #{count})
        end
        lines << '# HELP eventos_publicados_total Eventos publicados al broker'
        lines << '# TYPE eventos_publicados_total counter'
        @event_counts.each do |routing_key, count|
          lines << %(eventos_publicados_total{routing_key="#{escape_label(routing_key)}"} #{count})
        end
        "#{lines.join("\n")}\n"
      end

      def fallback_labels(method, route, code)
        %({method="#{escape_label(method)}",route="#{escape_label(route)}",code="#{escape_label(code)}"})
      end

      def escape_label(value)
        value.to_s.gsub('\\', '\\\\\\\\').gsub('"', '\\"').gsub("\n", '\\n')
      end
    end
  end
end
