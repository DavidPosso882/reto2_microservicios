# frozen_string_literal: true

require 'json'

module Vacaciones
  # Consumer of the local employee replica (opción b).
  #
  # - Durable queue `q.vacaciones.empleados` bound to the durable topic exchange
  #   `ecosistema.eventos` with keys `empleado.creado` and `empleado.retirado`.
  # - Deduplication by envelope `id` (tabla `eventos_procesados`).
  # - Manual ACK AFTER persisting the effect + the dedup mark.
  # - Backoff with retries while the broker is not ready at startup.
  class EmpleadosConsumer
    EXCHANGE = 'ecosistema.eventos'
    QUEUE = 'q.vacaciones.empleados'
    ROUTING_KEYS = %w[empleado.creado empleado.retirado].freeze
    BACKOFF_INICIAL = 2
    BACKOFF_MAX = 30

    def initialize(db, empleados_repo, logger, config, sleep_fn: ->(s) { sleep(s) })
      @db = db
      @empleados = empleados_repo
      @logger = logger
      @config = config
      @sleep_fn = sleep_fn
      @stop = false
    end

    def stop!
      @stop = true
    end

    # Runs in a background thread; never crashes the service if the broker is down.
    def run
      intento = 0
      until @stop
        begin
          conectar_y_consumir
        rescue StandardError => e
          @logger.error("[consumer] error de conexión/consumo: #{e.class}: #{e.message}")
        end
        break if @stop

        espera = [BACKOFF_INICIAL * (2**intento), BACKOFF_MAX].min
        intento += 1
        @logger.info("[consumer] reintentando en #{espera}s (intento #{intento})...")
        @sleep_fn.call(espera)
      end
    end

    def conectar_y_consumir
      require 'bunny'
      connection = Bunny.new(
        host: @config.rabbitmq_host,
        port: @config.rabbitmq_port,
        user: @config.rabbitmq_user,
        password: @config.rabbitmq_password,
        automatically_recover: true
      )
      connection.start
      @logger.info("[consumer] conectado a RabbitMQ en #{@config.rabbitmq_host}:#{@config.rabbitmq_port}")
      channel = connection.create_channel
      channel.prefetch(1)
      exchange = channel.topic(EXCHANGE, durable: true)
      queue = channel.queue(QUEUE, durable: true)
      ROUTING_KEYS.each { |key| queue.bind(exchange, routing_key: key) }
      @logger.info("[consumer] cola #{QUEUE} enlazada a #{ROUTING_KEYS.join(', ')}")

      queue.subscribe(manual_ack: true, block: true) do |delivery_info, _properties, body|
        procesar_mensaje(channel, delivery_info, body)
      end
    end

    # Handles one delivery: persist effect + dedup mark in ONE transaction,
    # then manual ACK. Returns :procesado, :duplicado or :descartado.
    def procesar_mensaje(channel, delivery_info, body)
      envelope = JSON.parse(body)
      event_id = envelope['id']
      type = envelope['type']

      if !event_id.is_a?(String) || event_id.empty? || !ROUTING_KEYS.include?(type)
        @logger.warn("[consumer] evento inválido (type=#{type.inspect}); se ACK y descarta")
        channel.ack(delivery_info.delivery_tag)
        return :descartado
      end

      ya_procesado = false
      @db.with_transaction do |conn|
        dup = conn.exec_params('SELECT 1 FROM eventos_procesados WHERE id = $1', [event_id])
        if dup.ntuples.positive?
          ya_procesado = true
          next
        end

        aplicar_evento(type, envelope['data'] || {})
        conn.exec_params('INSERT INTO eventos_procesados (id) VALUES ($1)', [event_id])
      end

      channel.ack(delivery_info.delivery_tag)
      if ya_procesado
        @logger.info("[consumer] evento duplicado #{event_id} (#{type}); ACK sin efecto")
        :duplicado
      else
        @logger.info("[consumer] evento #{type} procesado (id=#{event_id})")
        :procesado
      end
    rescue StandardError => e
      @logger.error("[consumer] fallo procesando evento #{event_id rescue 'desconocido'}: #{e.class}: #{e.message}; se reencola")
      channel.nack(delivery_info.delivery_tag, requeue: true) if channel
      :reencolado
    end

    private

    def aplicar_evento(type, data)
      case type
      when 'empleado.creado'
        @empleados.upsert(data)
      when 'empleado.retirado'
        @empleados.marcar_retirado(data)
      end
    end
  end
end
