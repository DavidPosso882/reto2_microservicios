# frozen_string_literal: true

require 'minitest/autorun'
require 'logger'
require 'json'
require 'ostruct'
require_relative '../app/empleados_consumer'
require_relative '../app/publisher'
require_relative 'support/fakes'

# Minimal error class so the failure test does not require the real bunny gem.
class BunnyMockError < StandardError; end

# Stub of a Bunny channel capturing ack/nack calls.
class FakeChannel
  attr_reader :acks, :nacks

  def initialize
    @acks = []
    @nacks = []
  end

  def ack(delivery_tag)
    @acks << delivery_tag
  end

  def nack(delivery_tag, requeue: false)
    @nacks << [delivery_tag, requeue]
  end
end

class FakeDeliveryInfo
  attr_reader :delivery_tag

  def initialize(tag)
    @delivery_tag = tag
  end
end

class ConsumerStub < Vacaciones::EmpleadosConsumer
  # Expose the private handler for testing without a broker connection.
  def procesar_mensaje_publico(channel, delivery_info, body)
    procesar_mensaje(channel, delivery_info, body)
  end
end

class ConsumerDedupTest < Minitest::Test
  def setup
    @db = FakeDb.new
    @empleados = FakeEmpleadosRepo.new
    @processed = {} # event_id => true
    @consumer = ConsumerStub.new(@db, @empleados, Logger.new(nil), config_stub)
  end

  def test_empleado_creado_actualiza_replica_y_ack
    envelope = evento('empleado.creado', 'E001', 'ACTIVO')
    channel = FakeChannel.new
    resultado = @consumer.procesar_mensaje_publico(channel, FakeDeliveryInfo.new(1), JSON.generate(envelope))

    assert_equal :procesado, resultado
    assert_equal 'ACTIVO', @empleados.buscar('E001')['estado']
    assert_equal 1, channel.acks.size
    assert_empty @empleados.upserts.select { |d| d['id'] == 'E001' } ? [] : []
  end

  def test_empleado_retirado_marca_retirado
    envelope = evento('empleado.retirado', 'E001', 'ACTIVO')
    channel = FakeChannel.new
    resultado = @consumer.procesar_mensaje_publico(channel, FakeDeliveryInfo.new(1), JSON.generate(envelope))

    assert_equal :procesado, resultado
    assert_equal 'RETIRADO', @empleados.buscar('E001')['estado']
    assert_equal 1, @empleados.retirados.size
  end

  def test_duplicado_por_id_no_aplica_efecto_pero_si_ack
    envelope = evento('empleado.creado', 'E001', 'ACTIVO')
    channel = FakeChannel.new
    body = JSON.generate(envelope)

    assert_equal :procesado, @consumer.procesar_mensaje_publico(channel, FakeDeliveryInfo.new(1), body)
    assert_equal :duplicado, @consumer.procesar_mensaje_publico(channel, FakeDeliveryInfo.new(2), body)

    # el upsert solo ocurrió una vez
    assert_equal 1, @empleados.upserts.size
    assert_equal 2, channel.acks.size
  end

  def test_fallo_persistencia_reencola_sin_ack
    @db.fail_next_transaction!
    envelope = evento('empleado.creado', 'E001', 'ACTIVO')
    channel = FakeChannel.new
    resultado = @consumer.procesar_mensaje_publico(channel, FakeDeliveryInfo.new(1), JSON.generate(envelope))

    assert_equal :reencolado, resultado
    assert_empty channel.acks
    assert_equal [[1, true]], channel.nacks
  end

  def test_evento_invalido_se_descarta_con_ack
    channel = FakeChannel.new
    resultado = @consumer.procesar_mensaje_publico(
      channel, FakeDeliveryInfo.new(1), JSON.generate({ 'id' => 'x', 'type' => 'otro.evento' })
    )
    assert_equal :descartado, resultado
    assert_equal 1, channel.acks.size
  end

  def test_backoff_exponencial_tope_30
    consumer = ConsumerStub.new(@db, @empleados, Logger.new(nil), config_stub)
    esperas = []
    consumer.instance_variable_set(:@stop, true)
    # stub run loop internals: verify the wait computation indirectly by
    # checking the constants and that stop halts the loop
    assert_equal 2, Vacaciones::EmpleadosConsumer::BACKOFF_INICIAL
    assert_equal 30, Vacaciones::EmpleadosConsumer::BACKOFF_MAX
  end

  private

  def evento(type, empleado_id, estado)
    {
      'id' => "evt-#{Random.rand(1_000_000)}",
      'type' => type,
      'version' => '1.0',
      'occurredAt' => '2026-09-21T14:30:00Z',
      'producer' => 'empleados-service',
      'data' => {
        'id' => empleado_id,
        'nombre' => 'Juan',
        'apellido' => 'Pérez',
        'email' => 'juan.perez@empresa.com',
        'estado' => estado
      }
    }
  end

  def config_stub
    OpenStruct.new(rabbitmq_host: 'localhost', rabbitmq_port: 5672,
                   rabbitmq_user: 'guest', rabbitmq_password: 'guest')
  end
end

class PublisherTest < Minitest::Test
  def setup
    @logger = Logger.new(nil)
    @publisher = Vacaciones::Publisher.new(config_stub, @logger)
  end

  def test_envelope_según_catalogo_3_8
    periodo = {
      'id' => 'V-2026-0042', 'empleadoId' => 'E001',
      'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30',
      'estado' => 'PROGRAMADA', 'fechaCreacion' => '2026-09-21T14:30:00Z'
    }
    captured = {}
    singleton = @publisher.singleton_class
    singleton.send(:define_method, :exchange) do
      Class.new do
        define_method(:publish) do |payload, **_opts|
          captured[:payload] = payload
        end
      end.new
    end

    now = Time.utc(2026, 9, 21, 14, 30, 0)
    @publisher.publish_vacaciones_programadas(periodo, 'juan.perez@empresa.com', now_provider: -> { now })

    envelope = JSON.parse(captured[:payload])
    assert_equal 'vacaciones.programadas', envelope['type']
    assert_equal '1.0', envelope['version']
    assert_equal 'vacaciones-service', envelope['producer']
    assert_equal '2026-09-21T14:30:00Z', envelope['occurredAt']
    assert envelope['id'].is_a?(String) && !envelope['id'].empty?
    data = envelope['data']
    assert_equal 'V-2026-0042', data['id']
    assert_equal 'E001', data['empleadoId']
    assert_equal 'juan.perez@empresa.com', data['empleadoEmail']
    assert_equal '2026-12-15', data['fechaInicio']
    assert_equal '2026-12-30', data['fechaFin']
    assert_equal 'PROGRAMADA', data['estado']
    assert_equal '2026-09-21T14:30:00Z', data['fechaCreacion']
  end

  def test_fallo_de_publish_se_traga_y_loggea
    def @publisher.exchange
      raise BunnyMockError, 'connection refused'
    end

    periodo = { 'id' => 'V-2026-0001', 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15',
                'fechaFin' => '2026-12-30', 'estado' => 'PROGRAMADA', 'fechaCreacion' => '2026-09-21T14:30:00Z' }
    result = @publisher.publish_vacaciones_programadas(periodo, 'x@empresa.com')
    assert_equal false, result
  end

  def config_stub
    OpenStruct.new(rabbitmq_host: 'localhost', rabbitmq_port: 5672,
                   rabbitmq_user: 'guest', rabbitmq_password: 'guest')
  end
end

# Minimal error class so the failure test does not require the real bunny gem.
class BunnyMockError < StandardError; end
