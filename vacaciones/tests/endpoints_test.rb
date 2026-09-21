# frozen_string_literal: true

require 'minitest/autorun'
require_relative '../app/endpoints'
require_relative 'support/fakes'

class EndpointsTest < Minitest::Test
  def setup
    @hoy = Date.new(2026, 9, 21)
    @empleados = FakeEmpleadosRepo.new(
      'E001' => { 'empleado_id' => 'E001', 'email' => 'juan.perez@empresa.com', 'nombre' => 'Juan', 'estado' => 'ACTIVO' }
    )
    @vacaciones = FakeVacacionesRepo.new
    @publisher = FakePublisher.new
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { @hoy })
    @id_generator = FakeIdGenerator.new(['V-2026-0001', 'V-2026-0002', 'V-2026-0003'])
    @endpoints = Vacaciones::Endpoints.new(
      empleados_repo: @empleados,
      vacaciones_repo: @vacaciones,
      id_generator: @id_generator,
      validations: @validations,
      publisher: @publisher,
      today_provider: -> { @hoy }
    )
  end

  def test_create_201_genera_id_del_servidor_y_publica_tras_save
    status, body = @endpoints.create(
      { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    )
    assert_equal 201, status
    assert_equal 'V-2026-0001', body['id']
    assert_equal 'PROGRAMADA', body['estado']
    assert_equal 'E001', body['empleadoId']
    assert_equal '2026-12-15', body['fechaInicio']
    assert_equal '2026-12-30', body['fechaFin']
    assert !body['fechaCreacion'].nil?

    # publish ocurre DESPUÉS del save, con el email desde la réplica local
    assert_equal 1, @publisher.publicaciones.size
    periodo, email = @publisher.publicaciones.first
    assert_equal 'V-2026-0001', periodo['id']
    assert_equal 'juan.perez@empresa.com', email
  end

  def test_create_400_con_mensaje_y_sin_publicar
    status, body = @endpoints.create(
      { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-30', 'fechaFin' => '2026-12-15' }
    )
    assert_equal 400, status
    assert_includes body['error'], 'fechaFin'
    assert_empty @publisher.publicaciones
  end

  def test_create_400_solapamiento_incluye_conflicto
    @endpoints.create({ 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' })
    @id_generator = FakeIdGenerator.new(['V-2026-0002'])
    status, body = @endpoints.create(
      { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-20', 'fechaFin' => '2027-01-10' }
    )
    assert_equal 400, status
    assert_includes body['error'], 'solapa'
    assert_equal 'V-2026-0001', body['conflicto']['id']
  end

  def test_create_400_empleado_desconocido_o_retirado_no_publica
    status, body = @endpoints.create(
      { 'empleadoId' => 'E999', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    )
    assert_equal 400, status
    assert_includes body['error'], 'E999'
    assert_empty @publisher.publicaciones
  end

  def test_create_publica_aunque_el_broker_falle_sin_rollback
    @publisher.fail_next_publication!
    status, body = @endpoints.create(
      { 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' }
    )
    # el publisher traga el fallo (log, sin rollback de BD): el save queda
    # persistido y la respuesta es 201 igual.
    assert_equal 201, status
    assert_equal 'V-2026-0001', body['id']
    assert_equal 1, @vacaciones.guardados.size
    assert_equal 1, @publisher.fallos.size
    assert_empty @publisher.publicaciones
  end

  def test_index_lista_y_filtra
    @endpoints.create({ 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' })
    @empleados.upsert({ 'id' => 'E002', 'email' => 'm@empresa.com', 'nombre' => 'M', 'estado' => 'ACTIVO' })
    @endpoints.create({ 'empleadoId' => 'E002', 'fechaInicio' => '2026-11-01', 'fechaFin' => '2026-11-10' })

    status, all = @endpoints.index
    assert_equal 200, status
    assert_equal 2, all.size

    _status, filtrado = @endpoints.index('E002')
    assert_equal 1, filtrado.size
    assert_equal 'E002', filtrado.first['empleadoId']
  end

  def test_show_200_y_404
    @endpoints.create({ 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' })
    status, body = @endpoints.show('V-2026-0001')
    assert_equal 200, status
    assert_equal 'V-2026-0001', body['id']

    status, body = @endpoints.show('V-9999-9999')
    assert_equal 404, status
    assert_equal 404, body['status']
    assert_includes body['error'], 'no existe'
  end

  def test_delete_cancela_si_aun_no_inicio
    @endpoints.create({ 'empleadoId' => 'E001', 'fechaInicio' => '2026-12-15', 'fechaFin' => '2026-12-30' })
    status, body = @endpoints.destroy('V-2026-0001')
    assert_equal 200, status
    assert_equal 'CANCELADA', body['estado']
  end

  def test_delete_400_si_ya_inicio
    @vacaciones = FakeVacacionesRepo.new([
      { 'id' => 'V-2026-0009', 'empleadoId' => 'E001', 'fechaInicio' => '2026-09-21',
        'fechaFin' => '2026-09-30', 'estado' => 'PROGRAMADA', 'fechaCreacion' => '2026-09-20T10:00:00Z' }
    ])
    rebuild_endpoints
    status, body = @endpoints.destroy('V-2026-0009')
    assert_equal 400, status
    assert_equal 400, body['status']
    assert_includes body['error'], 'ya inició'
  end

  def test_delete_404_si_no_existe
    status, body = @endpoints.destroy('V-9999-9999')
    assert_equal 404, status
    assert_equal 404, body['status']
  end

  private

  def rebuild_endpoints
    @validations = Vacaciones::Validations.new(@empleados, @vacaciones, today_provider: -> { @hoy })
    @endpoints = Vacaciones::Endpoints.new(
      empleados_repo: @empleados,
      vacaciones_repo: @vacaciones,
      id_generator: @id_generator,
      validations: @validations,
      publisher: @publisher,
      today_provider: -> { @hoy }
    )
  end
end
