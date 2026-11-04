# frozen_string_literal: true

require 'json'

require_relative 'observability'

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

    def initialize(db, empleados_repo, logger, config, vacaciones_repo = nil, sleep_fn: ->(s) { sleep(s) })
      @db = db
      @empleados = empleados_repo
      @logger = logger
      @config = config
      @vacaciones = vacaciones_repo
      @sleep_fn = sleep_fn
      @stop = false
      @connected = false
    end

    def stop!
      @stop = true
      @connected = false
    end

    # Estado observable para /health (conectividad real con el broker).
    def connected?
      @connected == true
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
      @connected = true
      @logger.info("[consumer] conectado a RabbitMQ en #{@config.rabbitmq_host}:#{@config.rabbitmq_port}")
      channel = connection.create_channel
      channel.prefetch(1)
      exchange = channel.topic(EXCHANGE, durable: true)
      queue = channel.queue(QUEUE, durable: true)
      ROUTING_KEYS.each { |key| queue.bind(exchange, routing_key: key) }
      @logger.info("[consumer] cola #{QUEUE} enlazada a #{ROUTING_KEYS.join(', ')}")

      queue.subscribe(manual_ack: true, block: true) do |delivery_info, properties, body|
        headers = properties.respond_to?(:headers) ? properties.headers : nil
        procesar_mensaje(channel, delivery_info, body, headers)
      end
    rescue StandardError
      @connected = false
      raise
    end

    # Handles one delivery: persist effect + dedup mark in ONE transaction,
    # then manual ACK. Returns :procesado, :duplicado or :descartado.
    #
    # Reto 8: extrae el contexto W3C de las cabeceras AMQP para continuar la
    # traza distribuida publicada por vacaciones-service (scheduler) o por
    # empleados-service.
    def procesar_mensaje(channel, delivery_info, body, headers = nil)
      event_id = nil
      Observability.with_context(headers) do
        Observability.tracer.in_span('vacaciones.consumir_empleado') do |span|
          envelope = JSON.parse(body)
          event_id = envelope['id']
          type = envelope['type']
          span.set_attribute('event.type', type.to_s)
          span.set_attribute('event.id', event_id.to_s)

          if !event_id.is_a?(String) || event_id.empty? || !ROUTING_KEYS.include?(type)
            @logger.warn("[consumer] evento inválido (type=#{type.inspect}); se ACK y descarta")
            channel.ack(delivery_info.delivery_tag)
            next :descartado
          end

          ya_procesado = false
          @db.with_transaction do |conn|
            dup = conn.exec_params('SELECT 1 FROM eventos_procesados WHERE id = $1', [event_id])
            if dup.ntuples.positive?
              ya_procesado = true
              next
            end

            aplicar_evento(type, envelope['data'] || {}, envelope['occurredAt'])
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
        end
      end
    rescue StandardError => e
      @logger.error("[consumer] fallo procesando evento #{event_id rescue 'desconocido'}: #{e.class}: #{e.message}; se reencola")
      channel.nack(delivery_info.delivery_tag, requeue: true) if channel
      :reencolado
    end

    private

    def aplicar_evento(type, data, occurred_at = nil)
      case type
      when 'empleado.creado'
        @empleados.upsert(data)
      when 'empleado.retirado'
        @empleados.marcar_retirado(data)
        # Las PROGRAMADA futuras del retirado no pueden seguir vigentes:
        # se cancelan en la misma transacción (auditoría conserva CANCELADA).
        # EN_CURSO no se toca (caso borde Reto 5: debe llegar a FINALIZADA
        # sin reactivar la cuenta) y el scheduler ya no lo toma como candidato
        # porque por_iniciar solo mira PROGRAMADA.
        if @vacaciones
          fecha_retiro = data['fechaRetiro'] || occurred_at
          canceladas = @vacaciones.cancelar_futuras_por_retiro(data['id'], fecha_retiro)
          @logger.info("[consumer] retiro #{data['id']}: #{canceladas.size} vacaciones futuras canceladas")
        end
      end
    end
  end
end
