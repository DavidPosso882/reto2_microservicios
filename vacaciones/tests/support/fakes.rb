# frozen_string_literal: true

require 'date'
require 'time'

# In-memory fakes used by the test suite (no Postgres, no RabbitMQ required).
# They mimic the exact query surface the repos expose.

class FakeDb
  attr_reader :eventos_procesados
  attr_accessor :fail_transaction_once

  def initialize
    @eventos_procesados = {}
    @fail_transaction_once = false
  end

  def connection
    self
  end

  # Mimics the two statements the consumer runs inside its transaction:
  # dedup SELECT and the INSERT into eventos_procesados.
  def exec_params(sql, params)
    if sql.include?('eventos_procesados')
      if sql.strip.start_with?('SELECT')
        @eventos_procesados.key?(params[0]) ? FakeResult.new([{ 'id' => params[0] }]) : FakeResult.new
      else
        @eventos_procesados[params[0]] = Time.now
        FakeResult.new
      end
    else
      FakeResult.new
    end
  end

  def with_transaction
    raise PG::ConnectionBad, 'boom simulado' if @fail_transaction_once

    yield self
  end

  # Allows tests to simulate a failed transaction once.
  def fail_next_transaction!
    @fail_transaction_once = true
  end
end

# Minimal stand-in for PG::Result usage in fakes (Array-like).
class FakeResult < Array
  def ntuples
    size
  end

  def [](index)
    at(index)
  end
end

class FakeEmpleadosRepo
  attr_reader :upserts, :retirados

  def initialize(data = {})
    @data = data
    @upserts = []
    @retirados = []
  end

  def buscar(empleado_id)
    @data[empleado_id]
  end

  def upsert(data)
    @upserts << data
    @data[data['id']] = { 'empleado_id' => data['id'], 'email' => data['email'].to_s,
                          'nombre' => data['nombre'].to_s, 'estado' => data['estado'].to_s }
  end

  def marcar_retirado(data)
    @retirados << data
    existing = @data[data['id']] || { 'email' => '', 'nombre' => '' }
    @data[data['id']] = { 'empleado_id' => data['id'], 'email' => data['email'].to_s,
                          'nombre' => data['nombre'].to_s, 'estado' => 'RETIRADO' }.merge(
                            'email' => data['email'].to_s
                          )
  end
end

class FakeVacacionesRepo
  attr_reader :guardados, :canceladas, :solapamiento_consultas

  def initialize(periodos = [])
    @periodos = periodos
    @guardados = []
    @canceladas = []
    @solapamiento_consultas = []
    @seq = 0
  end

  def todos(empleado_id: nil)
    empleado_id ? @periodos.select { |p| p['empleadoId'] == empleado_id } : @periodos
  end

  def buscar(id)
    @periodos.find { |p| p['id'] == id }
  end

  def buscar_solapamiento(empleado_id, fecha_inicio, fecha_fin)
    @solapamiento_consultas << [empleado_id, fecha_inicio, fecha_fin]
    @periodos.find do |p|
      p['empleadoId'] == empleado_id &&
        %w[PROGRAMADA EN_CURSO].include?(p['estado']) &&
        p['fechaInicio'] <= fecha_fin.iso8601 && p['fechaFin'] >= fecha_inicio.iso8601
    end
  end

  def crear(empleado_id:, fecha_inicio:, fecha_fin:, id_generator:, now_provider: -> { Time.now.utc })
    resultado = {
      'id' => id_generator.next_id(self),
      'empleadoId' => empleado_id,
      'fechaInicio' => fecha_inicio.iso8601,
      'fechaFin' => fecha_fin.iso8601,
      'estado' => 'PROGRAMADA',
      'fechaCreacion' => now_provider.call.iso8601
    }
    @periodos << resultado
    @guardados << resultado
    resultado
  end

  def cancelar(id)
    period = @periodos.find { |p| p['id'] == id }
    return nil if period.nil? || Date.parse(period['fechaInicio']) <= Date.today

    period = period.merge('estado' => 'CANCELADA')
    idx = @periodos.index { |p| p['id'] == id }
    @periodos[idx] = period
    @canceladas << period
    period
  end

  def cancelar_futuras_por_retiro(empleado_id, fecha_retiro = nil)
    corte = parse_corte(fecha_retiro) || Date.today
    afectadas = []
    @periodos = @periodos.map do |p|
      if p['empleadoId'] == empleado_id && p['estado'] == 'PROGRAMADA' && Date.parse(p['fechaInicio']) > corte
        cancelada = p.merge('estado' => 'CANCELADA')
        @canceladas << cancelada
        afectadas << cancelada
        cancelada
      else
        p
      end
    end
    afectadas
  end

  def parse_corte(value)
    return nil if value.nil? || value.to_s.strip.empty?

    Date.parse(value.to_s)
  rescue ArgumentError
    nil
  end
end

class FakePublisher
  attr_reader :publicaciones, :fallos

  def initialize
    @publicaciones = []
    @fallos = []
    @fail_next = false
  end

  def fail_next_publication!
    @fail_next = true
  end

  # Mimics the real Publisher contract: a publish failure is swallowed
  # (logged in the real one) and never propagates to the caller.
  def publish_vacaciones_programadas(periodo, empleado_email, _now_provider = nil)
    if @fail_next
      @fail_next = false
      @fallos << [periodo, empleado_email]
      return false
    end
    @publicaciones << [periodo, empleado_email]
    true
  end
end

class FakeIdGenerator
  def initialize(ids)
    @ids = ids.each
  end

  def next_id(_conn)
    @ids.next
  end
end
