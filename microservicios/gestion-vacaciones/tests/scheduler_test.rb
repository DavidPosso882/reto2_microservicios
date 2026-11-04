# frozen_string_literal: true

require 'minitest/autorun'
require 'logger'
require 'json'
require 'ostruct'
require 'date'
require_relative '../app/scheduler'
require_relative '../app/config'
require_relative '../app/vacaciones_repo'
require_relative '../app/publisher'
require_relative 'support/fakes'

# ── Reto 5: transiciones del scheduler (PROGRAMADA→EN_CURSO→FINALIZADA) ──────
class SchedulerTransitionTest < Minitest::Test
  HOY = Date.new(2026, 9, 28)

  def setup
    @hoy = HOY
    @empleados = FakeEmpleadosRepo.new(
      'E001' => { 'empleado_id' => 'E001', 'email' => 'juan.perez@empresa.com', 'nombre' => 'Juan', 'estado' => 'ACTIVO' }
    )
    @repo = FakeVacacionesRepo.new
    @publisher = FakePublisher.new
    @logger = Logger.new(nil)
    @scheduler = Vacaciones::Scheduler.new(@repo, @publisher, @empleados, @logger, 60,
                                           today_provider: -> { @hoy })
  end

  def programar(id, fecha_inicio, fecha_fin, estado = 'PROGRAMADA')
    periodo = { 'id' => id, 'empleadoId' => 'E001', 'fechaInicio' => fecha_inicio,
                'fechaFin' => fecha_fin, 'estado' => estado, 'fechaCreacion' => '2026-09-21T10:00:00Z' }
    @repo.agregar(periodo)
  end

  def test_inicia_programada_con_fechaInicio_hoy_o_pasada_y_publica_iniciadas
    programar('V-2026-0001', '2026-09-20', '2026-12-30') # inicio pasado
    programar('V-2026-0002', '2026-09-28', '2026-12-20') # inicio = hoy (estrategia demo)
    programar('V-2026-0003', '2026-09-29', '2026-12-20') # futuro: no debe tocar

    iniciadas, _ = @scheduler.tick

    assert_equal 'EN_CURSO', @repo.buscar('V-2026-0001')['estado']
    assert_equal 'EN_CURSO', @repo.buscar('V-2026-0002')['estado']
    assert_equal 'PROGRAMADA', @repo.buscar('V-2026-0003')['estado']
    assert_equal 2, @publisher.iniciadas.size
    assert_equal %w[V-2026-0001 V-2026-0002], @publisher.iniciadas.map { |p, _e| p['id'] }.sort
    assert_equal 2, iniciadas
  end

  def test_iniciadas_publica_con_email_de_la_replica
    programar('V-2026-0001', '2026-09-28', '2026-12-20')

    @scheduler.tick

    periodo, email = @publisher.iniciadas.first
    assert_equal 'V-2026-0001', periodo['id']
    assert_equal 'EN_CURSO', periodo['estado']
    assert_equal 'juan.perez@empresa.com', email
  end

  def test_inicia_aun_si_el_empleado_no_esta_en_la_replica_email_nil
    programar('V-2026-0001', '2026-09-28', '2026-12-20')
    @empleados = FakeEmpleadosRepo.new # réplica vacía (empleado nunca llegó)
    scheduler = Vacaciones::Scheduler.new(@repo, @publisher, @empleados, @logger, 60,
                                          today_provider: -> { @hoy })

    scheduler.tick

    assert_equal 1, @publisher.iniciadas.size
    assert_nil @publisher.iniciadas.first[1]
    assert_equal 'EN_CURSO', @repo.buscar('V-2026-0001')['estado']
  end

  def test_finaliza_en_curso_con_fechaFin_pasada_y_publica_finalizadas
    programar('V-2026-0001', '2026-09-20', '2026-09-27', 'EN_CURSO') # fechaFin < hoy
    programar('V-2026-0002', '2026-09-20', '2026-09-28', 'EN_CURSO') # fechaFin = hoy (inclusivo, demo hoy-hoy)
    programar('V-2026-0003', '2026-09-20', '2026-09-29', 'EN_CURSO') # fechaFin > hoy: sigue

    iniciadas, finalizadas = @scheduler.tick

    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0001')['estado']
    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0002')['estado']
    assert_equal 'EN_CURSO', @repo.buscar('V-2026-0003')['estado']
    assert_equal 2, @publisher.finalizadas.size
    assert_equal %w[V-2026-0001 V-2026-0002], @publisher.finalizadas.map { |p, _e| p['id'] }.sort
    assert_empty @publisher.iniciadas
    assert_equal [0, 2], [iniciadas, finalizadas]
  end

  def test_numera_ciclo_completo_en_un_tick
    programar('V-2026-0001', '2026-09-21', '2026-09-26') # PROGRAMADA, ya debería estar iniciado Y finalizado
    programar('V-2026-0002', '2026-09-20', '2026-09-27', 'EN_CURSO')

    @scheduler.tick

    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0001')['estado']
    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0002')['estado']
    assert_equal 1, @publisher.iniciadas.size
    assert_equal 2, @publisher.finalizadas.size
    assert_equal 'V-2026-0001', @publisher.iniciadas.first[0]['id']
    assert_includes @publisher.finalizadas.map { |p, _e| p['id'] }, 'V-2026-0001'
  end

  def test_estado_cancelado_y_finalizado_no_se_tocan
    programar('V-2026-0001', '2026-09-20', '2026-12-20', 'CANCELADA')
    programar('V-2026-0002', '2026-09-20', '2026-12-20', 'FINALIZADA')

    @scheduler.tick

    assert_equal 'CANCELADA', @repo.buscar('V-2026-0001')['estado']
    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0002')['estado']
    assert_empty @publisher.iniciadas
    assert_empty @publisher.finalizadas
  end

  def test_tick_repetido_no_duplica_publicaciones
    # fechaFin futura: queda EN_CURSO tras el primer tick (si fuera
    # fechaFin=hoy, la comparación inclusiva lo finalizaría en el mismo tick).
    programar('V-2026-0001', '2026-09-20', '2026-12-28')

    @scheduler.tick
    2.times { @scheduler.tick } # ya está EN_CURSO

    assert_equal 1, @publisher.iniciadas.size
    assert_equal 'EN_CURSO', @repo.buscar('V-2026-0001')['estado']

    # Simula el paso del día: deja fechaFin en el pasado y el estado en
    # EN_CURSO (mismo estado que dejó el tick anterior; el siguiente tick
    # por_finalizar lo encuentra). No hay atajo: usa la superficie real.
    periodo = @repo.buscar('V-2026-0001')
    periodo['fechaFin'] = '2026-09-27'

    2.times { @scheduler.tick }

    assert_equal 1, @publisher.finalizadas.size, 'FINALIZADA se publica exactamente una vez'
    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0001')['estado']
  end

  def test_periodo_hoy_hoy_inicia_y_finaliza_en_mismo_tick_sin_duplicar
    # Estrategia de demo del PDF: fechaInicio=hoy/fechaFin=hoy.
    programar('V-2026-0001', '2026-09-28', '2026-09-28')

    @scheduler.tick

    assert_equal 'FINALIZADA', @repo.buscar('V-2026-0001')['estado']
    assert_equal 1, @publisher.iniciadas.size
    assert_equal 1, @publisher.finalizadas.size

    @scheduler.tick # repetición: no vuelve a publicar nada

    assert_equal 1, @publisher.iniciadas.size
    assert_equal 1, @publisher.finalizadas.size
  end

  def test_transicion_condicional_evita_publicacion_si_otro_actor_ya_movo
    programar('V-2026-0001', '2026-09-28', '2026-12-20')
    # simula que otro tick/instancia ya lo movió después del SELECT del scheduler
    class << @repo
      def marcar_en_curso(id)
        nil # UPDATE con estado esperado afecta 0 filas
      end
    end

    @scheduler.tick

    assert_empty @publisher.iniciadas, 'sin transición real no hay evento'
    assert_equal 0, @repo.transiciones.size
  end

  def test_fallo_de_publish_no_rompe_el_tick_ni_revierte_estado
    programar('V-2026-0001', '2026-09-28', '2026-12-20')
    @publisher.fail_next_publication!

    iniciadas, = @scheduler.tick

    assert_equal 1, iniciadas
    assert_equal 'EN_CURSO', @repo.buscar('V-2026-0001')['estado']
    assert_empty @publisher.iniciadas
    assert_equal 1, @publisher.fallos.size
  end

  def test_marcar_en_curso_y_finalizada_son_idempotentes_a_nivel_repo
    programar('V-2026-0001', '2026-09-20', '2026-09-27')
    periodo = @repo.marcar_en_curso('V-2026-0001')
    assert_equal 'EN_CURSO', periodo['estado']

    finalizado = @repo.marcar_finalizada('V-2026-0001')
    assert_equal 'FINALIZADA', finalizado['estado']

    assert_nil @repo.marcar_en_curso('V-2026-0001')
    assert_nil @repo.marcar_finalizada('V-2026-0001')
  end

  def test_error_de_repo_en_un_tick_se_propaga_y_run_se_recupera
    programar('V-2026-0001', '2026-09-28', '2026-12-20')
    class << @repo
      def por_iniciar(_hoy)
        raise StandardError, 'boom simulado'
      end
    end

    # tick directo propaga (el rescue vive en run)
    assert_raises(StandardError) { @scheduler.tick }

    # El loop del run rescata el error y sigue: tras el primer tick (con repo
    # sano), el sleep_fn registra el intervalo y corta el loop cooperativamente.
    class << @repo
      def por_iniciar(_hoy)
        []
      end
    end
    sleeps = []
    scheduler = nil
    scheduler = Vacaciones::Scheduler.new(@repo, @publisher, @empleados, @logger, 60,
                                          sleep_fn: ->(s) { sleeps << s; scheduler.stop! },
                                          today_provider: -> { @hoy })
    scheduler.run

    assert_equal [60], sleeps
  end
end

# ── Reto 5: publicadores vacaciones.iniciadas / vacaciones.finalizadas ───────
class PublisherCicloVidaTest < Minitest::Test
  def setup
    @logger = Logger.new(nil)
    @publisher = Vacaciones::Publisher.new(config_stub, @logger)
  end

  def test_envelope_iniciadas_según_formato_definido
    periodo = {
      'id' => 'V-2026-0042', 'empleadoId' => 'E001',
      'fechaInicio' => '2026-09-28', 'fechaFin' => '2026-12-30',
      'estado' => 'EN_CURSO', 'fechaCreacion' => '2026-09-21T14:30:00Z'
    }
    capturado = capture_exchange
    now = Time.utc(2026, 9, 28, 12, 0, 0)

    @publisher.publish_vacaciones_iniciadas(periodo, 'juan.perez@empresa.com', now_provider: -> { now })

    envelope = JSON.parse(capturado[:payload])
    assert_equal 'vacaciones.iniciadas', envelope['type']
    assert_equal '1.0', envelope['version']
    assert_equal 'vacaciones-service', envelope['producer']
    assert_equal '2026-09-28T12:00:00Z', envelope['occurredAt']
    assert envelope['id'].is_a?(String) && !envelope['id'].empty?
    data = envelope['data']
    assert_equal 'V-2026-0042', data['id']
    assert_equal 'E001', data['empleadoId']
    assert_equal 'juan.perez@empresa.com', data['empleadoEmail']
    assert_equal '2026-09-28', data['fechaInicio']
    assert_equal '2026-12-30', data['fechaFin']
    assert_equal 'EN_CURSO', data['estado']
    assert_equal '2026-09-21T14:30:00Z', data['fechaCreacion']
  end

  def test_envelope_finalizadas_sigue_el_mismo_formato
    periodo = {
      'id' => 'V-2026-0042', 'empleadoId' => 'E001',
      'fechaInicio' => '2026-09-28', 'fechaFin' => '2026-09-28',
      'estado' => 'FINALIZADA', 'fechaCreacion' => '2026-09-21T14:30:00Z'
    }
    capturado = capture_exchange

    @publisher.publish_vacaciones_finalizadas(periodo, 'maria@empresa.com')

    envelope = JSON.parse(capturado[:payload])
    assert_equal 'vacaciones.finalizadas', envelope['type']
    assert_equal '1.0', envelope['version']
    assert_equal 'vacaciones-service', envelope['producer']
    assert_equal 'FINALIZADA', envelope['data']['estado']
    assert_equal 'maria@empresa.com', envelope['data']['empleadoEmail']
  end

  def test_fallo_de_publish_se_traga
    def @publisher.exchange
      raise BunnyMockError, 'connection refused'
    end

    periodo = { 'id' => 'V-2026-0001', 'empleadoId' => 'E001', 'fechaInicio' => '2026-09-28',
                'fechaFin' => '2026-12-30', 'estado' => 'EN_CURSO', 'fechaCreacion' => '2026-09-21T14:30:00Z' }
    assert_equal false, @publisher.publish_vacaciones_iniciadas(periodo, 'x@empresa.com')
  end

  private

  def capture_exchange
    capturado = {}
    @publisher.singleton_class.send(:define_method, :exchange) do
      Class.new do
        define_method(:publish) do |payload, **_opts|
          capturado[:payload] = payload
        end
      end.new
    end
    capturado
  end

  def config_stub
    OpenStruct.new(rabbitmq_host: 'localhost', rabbitmq_port: 5672,
                   rabbitmq_user: 'guest', rabbitmq_password: 'guest')
  end
end

# ── Reto 5: config de intervalo del scheduler ────────────────────────────────
class SchedulerConfigTest < Minitest::Test
  def test_default_60_segundos
    config = Vacaciones::Config.new({})
    assert_equal 60, config.scheduler_interval_s
  end

  def test_env_configure_intervalo
    config = Vacaciones::Config.new('SCHEDULER_INTERVAL_S' => '5')
    assert_equal 5, config.scheduler_interval_s
  end

  def test_valores_menos_de_1_se_suben_a_1
    config = Vacaciones::Config.new('SCHEDULER_INTERVAL_S' => '0')
    assert_equal 1, config.scheduler_interval_s
  end
end
