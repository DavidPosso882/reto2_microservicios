# frozen_string_literal: true

require 'minitest/autorun'
require_relative '../app/validations'
require_relative 'support/fakes'

# Reto 6 (Punto 1): ampliación de la tabla de decisión de POST /vacaciones.
#
# Cubre, solo con fakes (sin PostgreSQL ni RabbitMQ):
#   - solapamiento inclusivo: contiene, contenido, toca 1 día, idéntico y adyacente
#   - fechas incoherentes (fin < inicio, imposibles, ausentes, en blanco)
#   - fechas pasadas (antes de hoy)
#   - conteo de días con extremos inclusivos
#
# La convención del dominio es inclusiva en ambos extremos: el período
# 10..20 son 11 días y toca el 20 (mismo día) bloquea, pero empezar el 21
# (día siguiente al fin) no bloquea.
class SolapamientoTablaTest < Minitest::Test
  HOY = Date.new(2026, 9, 21)
  PERIODO_BASE = {
    'id' => 'V-2026-0001',
    'empleadoId' => 'E001',
    'fechaInicio' => '2026-12-10',
    'fechaFin' => '2026-12-20',
    'estado' => 'PROGRAMADA',
    'fechaCreacion' => '2026-09-20T10:00:00Z'
  }.freeze

  # [descripción, fechaInicio nuevo, fechaFin nuevo, empleado, ¿solapa?]
  CASOS_SOLAPAMIENTO = [
    ['contiene al período existente (nuevo más amplio)', '2026-12-05', '2026-12-25', 'E001', true],
    ['contenido en el período existente (nuevo más corto)', '2026-12-12', '2026-12-18', 'E001', true],
    ['mismo inicio, termina dentro', '2026-12-10', '2026-12-15', 'E001', true],
    ['mismo fin, empieza dentro', '2026-12-15', '2026-12-20', 'E001', true],
    ['idéntico al período existente', '2026-12-10', '2026-12-20', 'E001', true],
    ['toca 1 día por el borde inicial (fin nuevo == inicio existente)', '2026-12-01', '2026-12-10', 'E001', true],
    ['toca 1 día por el borde final (inicio nuevo == fin existente)', '2026-12-20', '2026-12-30', 'E001', true],
    ['un solo día dentro del período existente', '2026-12-15', '2026-12-15', 'E001', true],
    ['adyacente justo antes (fin nuevo + 1 día == inicio existente)', '2026-11-30', '2026-12-09', 'E001', false],
    ['adyacente justo después (inicio nuevo == fin existente + 1 día)', '2026-12-21', '2026-12-30', 'E001', false],
    ['separado por varios días', '2027-01-05', '2027-01-10', 'E001', false],
    ['otro empleado con rango idéntico', '2026-12-10', '2026-12-20', 'E003', false]
  ].freeze

  def setup
    @empleados = FakeEmpleadosRepo.new(
      'E001' => { 'empleado_id' => 'E001', 'email' => 'juan@empresa.com', 'nombre' => 'Juan', 'estado' => 'ACTIVO' },
      'E003' => { 'empleado_id' => 'E003', 'email' => 'ana@empresa.com', 'nombre' => 'Ana', 'estado' => 'ACTIVO' }
    )
    @vacaciones = FakeVacacionesRepo.new([PERIODO_BASE.dup])
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { HOY })
  end

  def test_tabla_de_solapamiento_inclusivo_completa
    CASOS_SOLAPAMIENTO.each do |descripcion, inicio, fin, empleado, solapa|
      attrs = { 'empleadoId' => empleado, 'fechaInicio' => inicio, 'fechaFin' => fin }
      errors = @validations.call(attrs)

      if solapa
        assert_equal 1, errors.length,
                     "Caso '#{descripcion}': se esperaba 1 error de solapamiento; errores: #{errors.map(&:message)}"
        assert_includes errors.first.message, 'solapa', "Caso '#{descripcion}'"
        assert_equal 'V-2026-0001', errors.first.conflicto['id'],
                     "Caso '#{descripcion}': el conflicto debe exponer el período existente"
      else
        assert_empty errors,
                     "Caso '#{descripcion}': no debía haber errores; errores: #{errors.map(&:message)}"
      end
    end
  end

  def test_la_consulta_de_solapamiento_envia_el_rango_completo
    @validations.call('empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-16')

    assert_equal [['E001', Date.new(2026, 12, 15), Date.new(2026, 12, 16)]],
                 @vacaciones.solapamiento_consultas
  end

  def test_estados_cancelada_y_finalizada_no_bloquean
    %w[CANCELADA FINALIZADA].each do |estado|
      repo = FakeVacacionesRepo.new([PERIODO_BASE.merge('estado' => estado)])
      validations = Vacaciones::Validations.new(@empleados, repo, today_provider: -> { HOY })

      attrs = { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-12', 'fechaFin' => '2026-12-18' }
      assert_empty validations.call(attrs), "Un período #{estado} no debe bloquear un nuevo registro"
    end
  end
end

class FechasIncoherentesTest < Minitest::Test
  HOY = Date.new(2026, 9, 21)

  def setup
    @empleados = FakeEmpleadosRepo.new(
      'E001' => { 'empleado_id' => 'E001', 'email' => 'juan@empresa.com', 'nombre' => 'Juan', 'estado' => 'ACTIVO' }
    )
    @vacaciones = FakeVacacionesRepo.new
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { HOY })
  end

  def attrs(inicio, fin)
    { 'empleadoId' => 'E001', 'fechaInicio' => inicio, 'fechaFin' => fin }
  end

  def test_fecha_fin_anterior_a_inicio_reporta_un_unico_error
    errors = @validations.call(attrs('2026-12-20', '2026-12-15'))

    assert_equal 1, errors.length
    assert_includes errors.first.message, 'fechaFin (2026-12-15)'
    assert_includes errors.first.message, 'fechaInicio (2026-12-20)'
  end

  def test_fecha_fin_igual_a_inicio_es_un_periodo_valido_de_un_dia
    assert_empty @validations.call(attrs('2026-12-15', '2026-12-15'))
  end

  def test_fechas_imposibles_en_el_calendario
    ['2026-02-30', '2026-13-01', '2026-00-10'].each do |fecha|
      errors = @validations.call(attrs(fecha, '2026-12-15'))
      assert(errors.any? { |e| e.message.include?('fechaInicio') },
             "#{fecha} debe rechazarse como fechaInicio")
    end

    errors = @validations.call(attrs('2026-12-15', '2026-02-30'))
    assert(errors.any? { |e| e.message.include?('fechaFin') },
           '2026-02-30 debe rechazarse como fechaFin')
  end

  def test_fechas_ausentes_reportan_ambos_errores_en_orden
    errors = @validations.call(attrs(nil, nil))

    assert_equal 2, errors.length
    assert_equal [
      'fechaInicio es obligatorio y debe tener formato YYYY-MM-DD',
      'fechaFin es obligatorio y debe tener formato YYYY-MM-DD'
    ], errors.map(&:message)
  end

  def test_fechas_en_blanco_reportan_ambos_errores
    errors = @validations.call(attrs('', '   '))

    assert_equal 2, errors.length
    assert_equal 2, errors.count { |e| e.message.include?('es obligatorio') }
  end

  def test_formato_no_fecha_se_rechaza
    errors = @validations.call(attrs('not-a-date', '2026-12-15'))

    assert_equal 1, errors.length
    assert_includes errors.first.message, 'fechaInicio'
  end
end

class FechasPasadasTest < Minitest::Test
  HOY = Date.new(2026, 9, 21)

  def setup
    @empleados = FakeEmpleadosRepo.new(
      'E001' => { 'empleado_id' => 'E001', 'email' => 'juan@empresa.com', 'nombre' => 'Juan', 'estado' => 'ACTIVO' }
    )
    @vacaciones = FakeVacacionesRepo.new
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { HOY })
  end

  def attrs(inicio, fin)
    { 'empleadoId' => 'E001', 'fechaInicio' => inicio, 'fechaFin' => fin }
  end

  def test_inicio_anterior_a_hoy_se_rechaza
    errors = @validations.call(attrs('2026-09-20', '2026-12-15'))

    assert_equal 1, errors.length
    assert_includes errors.first.message, 'no puede ser anterior a la fecha actual (2026-09-21)'
  end

  def test_inicio_hoy_es_valido
    assert_empty @validations.call(attrs('2026-09-21', '2026-12-15'))
  end

  def test_periodo_completo_en_el_pasado_reporta_solo_el_error_de_inicio
    errors = @validations.call(attrs('2026-08-01', '2026-08-10'))

    assert_equal 1, errors.length
    assert_includes errors.first.message, 'fechaInicio'
    assert_includes errors.first.message, 'anterior a la fecha actual'
  end

  def test_un_solo_dia_pasado_tambien_se_rechaza
    errors = @validations.call(attrs('2026-09-20', '2026-09-20'))

    assert_equal 1, errors.length
    assert_includes errors.first.message, 'anterior a la fecha actual'
  end
end

class CalculoDiasInclusivosTest < Minitest::Test
  HOY = Date.new(2026, 9, 21)

  def setup
    @vacaciones = FakeVacacionesRepo.new
  end

  # Conteo del dominio: ambos extremos cuentan (10..20 = 11 días).
  def dias_inclusivos(inicio, fin)
    (Vacaciones::Validations.parse_date(fin) - Vacaciones::Validations.parse_date(inicio)).to_i + 1
  end

  def test_conteo_inclusivo_de_periodos
    assert_equal 1, dias_inclusivos('2026-12-15', '2026-12-15')
    assert_equal 15, dias_inclusivos('2026-12-01', '2026-12-15')
    assert_equal 31, dias_inclusivos('2026-12-01', '2026-12-31')
  end

  def test_conteo_a_traves_de_fin_de_mes_y_de_año
    assert_equal 3, dias_inclusivos('2026-11-30', '2026-12-02')
    assert_equal 3, dias_inclusivos('2026-12-31', '2027-01-02')
  end

  def test_periodos_adyacentes_no_comparten_ningun_dia
    primero = dias_inclusivos('2026-12-10', '2026-12-20')
    segundo = dias_inclusivos('2026-12-21', '2026-12-30')

    assert_equal 11, primero
    assert_equal 10, segundo
    # Al ser adyacentes, los días suman exactamente el rango total (21), sin
    # solaparse: el 20 y el 21 son días distintos.
    assert_equal dias_inclusivos('2026-12-10', '2026-12-30'), primero + segundo
  end

  def test_crear_persiste_el_rango_de_un_dia_sin_desplazarlo
    id_generator = FakeIdGenerator.new(['V-2026-0001'])
    periodo = @vacaciones.crear(
      empleado_id: 'E001',
      fecha_inicio: Date.new(2026, 12, 15),
      fecha_fin: Date.new(2026, 12, 15),
      id_generator: id_generator,
      now_provider: -> { Time.utc(2026, 9, 21, 10, 0, 0) }
    )

    assert_equal '2026-12-15', periodo['fechaInicio']
    assert_equal '2026-12-15', periodo['fechaFin']
    assert_equal 1, dias_inclusivos(periodo['fechaInicio'], periodo['fechaFin'])
  end
end
