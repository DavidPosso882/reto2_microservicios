# frozen_string_literal: true

require 'minitest/autorun'
require_relative '../app/validations'
require_relative '../app/id_generator'
require_relative 'support/fakes'

class ValidacionesTest < Minitest::Test
  def setup
    @hoy = Date.new(2026, 9, 21)
    @empleados = FakeEmpleadosRepo.new(
      'E001' => { 'empleado_id' => 'E001', 'email' => 'juan.perez@empresa.com', 'nombre' => 'Juan', 'estado' => 'ACTIVO' },
      'E002' => { 'empleado_id' => 'E002', 'email' => 'maria@empresa.com', 'nombre' => 'Maria', 'estado' => 'RETIRADO' }
    )
    @vacaciones = FakeVacacionesRepo.new
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { @hoy })
  end

  def test_validacion_1_fecha_fin_no_posterior_a_fecha_inicio
    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-15' }
    errors = @validations.call(attrs)
    assert_equal 1, errors.length
    assert_includes errors.first.message, 'fechaFin'

    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-20', 'fechaFin' => '2026-12-15' }
    errors = @validations.call(attrs)
    assert_equal 1, errors.length
    assert_includes errors.first.message, 'fechaFin'
  end

  def test_validacion_2_fecha_inicio_anterior_a_hoy
    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-09-20', 'fechaFin' => '2026-12-15' }
    errors = @validations.call(attrs)
    assert_equal 1, errors.length
    assert_includes errors.first.message, 'no puede ser anterior'

    # hoy mismo es válido
    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-09-21', 'fechaFin' => '2026-12-15' }
    assert_empty @validations.call(attrs)
  end

  def test_validacion_3_solapamiento_incluye_periodo_en_conflicto
    @vacaciones = FakeVacacionesRepo.new([
      { 'id' => 'V-2026-0001', 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-10',
        'fechaFin' => '2026-12-20', 'estado' => 'PROGRAMADA', 'fechaCreacion' => '2026-09-20T10:00:00Z' }
    ])
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { @hoy })

    # cruce inclusivo: termina exactamente el día de inicio del otro
    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-20', 'fechaFin' => '2026-12-30' }
    errors = @validations.call(attrs)
    assert_equal 1, errors.length
    assert_equal 'V-2026-0001', errors.first.conflicto['id']

    # otro empleado con el mismo rango no genera conflicto
    @empleados.upsert({ 'id' => 'E003', 'email' => 'x@empresa.com', 'nombre' => 'X', 'estado' => 'ACTIVO' })
    attrs = { 'empleadoId' => 'E003', 'fechaInicio' => '2026-12-20', 'fechaFin' => '2026-12-30' }
    assert_empty @validations.call(attrs)
  end

  def test_validacion_3_no_conflictan_con_canceladas
    @vacaciones = FakeVacacionesRepo.new([
      { 'id' => 'V-2026-0001', 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-10',
        'fechaFin' => '2026-12-20', 'estado' => 'CANCELADA', 'fechaCreacion' => '2026-09-20T10:00:00Z' }
    ])
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { @hoy })

    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    assert_empty @validations.call(attrs)
  end

  def test_validacion_4_empleado_ausente_en_replica
    attrs = { 'empleadoId' => 'E999', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    errors = @validations.call(attrs)
    assert_equal 1, errors.length
    assert_includes errors.first.message, 'E999'
    assert_includes errors.first.message, 'réplica local'
  end

  def test_validacion_4_empleado_retirado
    attrs = { 'empleadoId' => 'E002', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    errors = @validations.call(attrs)
    assert_equal 1, errors.length
    assert_includes errors.first.message, 'RETIRADO'
  end

  def test_empleadoId_ausente
    attrs = { 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    errors = @validations.call(attrs)
    assert errors.any? { |e| e.message.include?('empleadoId') }
  end

  def test_fechas_invalidas
    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => 'not-a-date', 'fechaFin' => '2026-12-30' }
    errors = @validations.call(attrs)
    assert errors.any? { |e| e.message.include?('fechaInicio') }

    attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '' }
    errors = @validations.call(attrs)
    assert errors.any? { |e| e.message.include?('fechaFin') }
  end
end

class IdGeneratorTest < Minitest::Test
  class ConnStub
    def initialize(rows)
      @rows = rows
    end

    def exec_params(_sql, _params)
      @rows
    end
  end

  def test_formato_y_secuencia
    gen = Vacaciones::IdGenerator.new(clock: -> { Date.new(2026, 9, 21) })
    id = gen.next_id(ConnStub.new([{ 'id' => 'V-2026-0041' }]))
    assert_equal 'V-2026-0042', id
  end

  def test_primer_id_del_anio
    gen = Vacaciones::IdGenerator.new(clock: -> { Date.new(2027, 1, 5) })
    id = gen.next_id(ConnStub.new(FakeResult.new))
    assert_equal 'V-2027-0001', id
  end

  def test_formato_valido
    assert Vacaciones::IdGenerator.valid?('V-2026-0042')
    refute Vacaciones::IdGenerator.valid?('V-26-42')
    refute Vacaciones::IdGenerator.valid?(nil)
  end
end
