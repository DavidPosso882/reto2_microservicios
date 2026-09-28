# frozen_string_literal: true

require 'json'
require 'securerandom'
require 'time'

module Vacaciones
  # Publisher for `vacaciones.programadas` and (Reto 5) the lifecycle events
  # `vacaciones.iniciadas` / `vacaciones.finalizadas` (extensión del catálogo 3.8).
  # Publish failure is logged and swallowed: the DB write is NOT rolled back.
  class Publisher
    EXCHANGE = 'ecosistema.eventos'
    ROUTING_KEY = 'vacaciones.programadas'
    ROUTING_KEY_INICIADAS = 'vacaciones.iniciadas'
    ROUTING_KEY_FINALIZADAS = 'vacaciones.finalizadas'
    VERSION = '1.0'
    PRODUCER = 'vacaciones-service'

    def initialize(config, logger)
      @config = config
      @logger = logger
      @exchange = nil
      @mutex = Mutex.new
    end

    def publish_vacaciones_programadas(periodo, empleado_email, now_provider: -> { Time.now.utc })
      evento = envelope('vacaciones.programadas', periodo, empleado_email, now_provider)
      publish(ROUTING_KEY, JSON.generate(evento))
    end

    # Reto 5: vacaciones.iniciadas — un período PROGRAMADA pasa a EN_CURSO.
    def publish_vacaciones_iniciadas(periodo, empleado_email, now_provider: -> { Time.now.utc })
      evento = envelope('vacaciones.iniciadas', periodo, empleado_email, now_provider)
      publish(ROUTING_KEY_INICIADAS, JSON.generate(evento))
    end

    # Reto 5: vacaciones.finalizadas — un período EN_CURSO pasa a FINALIZADA.
    def publish_vacaciones_finalizadas(periodo, empleado_email, now_provider: -> { Time.now.utc })
      evento = envelope('vacaciones.finalizadas', periodo, empleado_email, now_provider)
      publish(ROUTING_KEY_FINALIZADAS, JSON.generate(evento))
    end

    def publish(routing_key, payload)
      exchange.publish(payload, routing_key: routing_key, persistent: true, content_type: 'application/json')
      true
    rescue StandardError => e
      @logger.error("[publisher] fallo publicando '#{routing_key}' (sin rollback de BD): #{e.class}: #{e.message}")
      false
    end

    def close
      @mutex.synchronize do
        begin
          @connection&.close
        rescue StandardError
          nil
        end
        @connection = nil
        @exchange = nil
      end
    end

    private

    # Shared envelope (formato catálogo §1): {id uuid, type, version 1.0,
    # occurredAt UTC ISO, producer vacaciones-service, data {...}}.
    def envelope(type, periodo, empleado_email, now_provider)
      {
        'id' => SecureRandom.uuid,
        'type' => type,
        'version' => VERSION,
        'occurredAt' => now_provider.call.iso8601,
        'producer' => PRODUCER,
        'data' => {
          'id' => periodo['id'],
          'empleadoId' => periodo['empleadoId'],
          'empleadoEmail' => empleado_email,
          'fechaInicio' => periodo['fechaInicio'],
          'fechaFin' => periodo['fechaFin'],
          'estado' => periodo['estado'],
          'fechaCreacion' => periodo['fechaCreacion']
        }
      }
    end

    # Lazily declares the durable topic exchange on first use and reuses it.
    def exchange
      @mutex.synchronize do
        @exchange ||= begin
          require 'bunny'
          @connection = Bunny.new(
            host: @config.rabbitmq_host,
            port: @config.rabbitmq_port,
            user: @config.rabbitmq_user,
            password: @config.rabbitmq_password,
            automatically_recover: true
          )
          @connection.start
          channel = @connection.create_channel
          channel.topic(EXCHANGE, durable: true)
        end
      end
    end
  end
end
