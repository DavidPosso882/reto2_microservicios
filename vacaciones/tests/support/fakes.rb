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
  attr_reader :guardados, :canceladas, :solapamiento_consultas, :transiciones

  def initialize(periodos = [])
    @periodos = periodos
    @guardados = []
    @canceladas = []
    @solapamiento_consultas = []
    @transiciones = []
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
    @canceladas << period
    reemplazar(period)
    period
  end

  # ── Reto 5: superficie usada por el Scheduler ──

  # PROGRAMADA con fechaInicio <= hoy: candidatos a EN_CURSO.
  def por_iniciar(hoy)
    @periodos.select { |p| p['estado'] == 'PROGRAMADA' && Date.parse(p['fechaInicio']) <= hoy }
  end

  # EN_CURSO con fechaFin <= hoy: candidatos a FINALIZADA (inclusivo, demo hoy-hoy).
  def por_finalizar(hoy)
    @periodos.select { |p| p['estado'] == 'EN_CURSO' && Date.parse(p['fechaFin']) <= hoy }
  end

  # UPDATE condicional PROGRAMADA->EN_CURSO: devuelve la fila o nil si el
  # estado ya no es el esperado (idempotencia, sin doble evento).
  def marcar_en_curso(id)
    transicionar(id, 'PROGRAMADA', 'EN_CURSO')
  end

  # UPDATE condicional EN_CURSO->FINALIZADA: misma semántica.
  def marcar_finalizada(id)
    transicionar(id, 'EN_CURSO', 'FINALIZADA')
  end

  # Helper de test: agrega un período sin pasar por crear().
  def agregar(periodo)
    @periodos << periodo
    periodo
  end

  private

  def transicionar(id, estado_esperado, estado_nuevo)
    period = @periodos.find { |p| p['id'] == id }
    return nil if period.nil? || period['estado'] != estado_esperado

    actualizado = period.merge('estado' => estado_nuevo)
    @transiciones << actualizado
    reemplazar(actualizado)
    actualizado
  end

  def reemplazar(periodo)
    idx = @periodos.index { |p| p['id'] == periodo['id'] }
    @periodos[idx] = periodo
    periodo
  end
end

class FakePublisher
  attr_reader :publicaciones, :fallos, :iniciadas, :finalizadas

  def initialize
    @publicaciones = []
    @fallos = []
    @iniciadas = []
    @finalizadas = []
    @fail_next = false
  end

  def fail_next_publication!
    @fail_next = true
  end

  # Mimics the real Publisher contract: a publish failure is swallowed
  # (logged in the real one) and never propagates to the caller.
  def publish_vacaciones_programadas(periodo, empleado_email, _now_provider = nil)
    registrar(periodo, empleado_email)
  end

  # Reto 5: vacaciones.iniciadas / vacaciones.finalizadas (mismo contrato,
  # con listas dedicadas para afirmar conteos exactos sin ambigüedad).
  def publish_vacaciones_iniciadas(periodo, empleado_email, _now_provider = nil)
    registrar(periodo, empleado_email, :iniciadas)
  end

  def publish_vacaciones_finalizadas(periodo, empleado_email, _now_provider = nil)
    registrar(periodo, empleado_email, :finalizadas)
  end

  private

  def registrar(periodo, empleado_email, lista_especifica = nil)
    if @fail_next
      @fail_next = false
      @fallos << [periodo, empleado_email]
      return false
    end
    @publicaciones << [periodo, empleado_email]
    case lista_especifica
    when :iniciadas then @iniciadas << [periodo, empleado_email]
    when :finalizadas then @finalizadas << [periodo, empleado_email]
    end
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
