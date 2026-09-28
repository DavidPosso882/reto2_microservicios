# frozen_string_literal: true

require 'date'

module Vacaciones
  # Reto 5: scheduler del ciclo de vida de las vacaciones.
  #
  # Corre en un hilo de fondo (mismo patrón que EmpleadosConsumer en Boot):
  # cada `SCHEDULER_INTERVAL_S` segundos (default 60, mínimo 1) aplica
  # transiciones de estado por FECHA (columnas DATE, sin hora):
  #
  #   PROGRAMADA con fechaInicio <= hoy -> EN_CURSO   + vacaciones.iniciadas
  #   EN_CURSO   con fechaFin   <= hoy -> FINALIZADA + vacaciones.finalizadas
  #
  # La comparación es INCLUSIVA (<=) en ambos casos: un período
  # fechaInicio=hoy/fechaFin=hoy (estrategia de demo del PDF) queda
  # demostrado dentro del mismo día — primer tick pasa a EN_CURSO y un
  # segundo tick (o el mismo, si los períodos ya cumplían la condición de
  # fin) lo finaliza. La opción por HORA exacta (comparar fecha+hora)
  # requeriría columnas TIMESTAMPTZ en la tabla vacaciones; queda
  # documentada como limitación en el README.
  #
  # Idempotencia: la transición se resuelve en SQL con
  # `UPDATE ... WHERE estado = '<estado esperado>' RETURNING *`; el evento
  # se publica SOLO si la fila efectivamente transicionó. Ticks repetidos
  # o filas ya en el estado final no vuelven a publicar (los períodos
  # EN_CURSO/FINALIZADA ya no son candidatos).
  #
  # Limitación conocida: con N instancias corriendo, cada una despertaría
  # y seleccionaría/actualizaría sin coordinación; el UPDATE condicional
  # evita dobles transiciones/eventos pero el SELECT-then-UPDATE queda racy
  # entre instancias. En el Reto 31 se resuelve con ShedLock.
  class Scheduler
    def initialize(repo, publisher, empleados_repo, logger, intervalo_s,
                   sleep_fn: ->(s) { sleep(s) }, today_provider: -> { Date.today })
      @repo = repo
      @publisher = publisher
      @empleados = empleados_repo
      @logger = logger
      @intervalo = [intervalo_s.to_i, 1].max
      @sleep_fn = sleep_fn
      @today_provider = today_provider
      @stop = false
    end

    # Cooperative stop: the loop finishes the current tick and exits.
    def stop!
      @stop = true
    end

    # Runs in a background thread; a tick error never crashes the service.
    def run
      until @stop
        begin
          tick
        rescue StandardError => e
          @logger.error("[scheduler] error en tick: #{e.class}: #{e.message}")
        end
        break if @stop

        @sleep_fn.call(@intervalo)
      end
    end

    # One pass over both transitions. Returns [iniciadas, finalizadas] counts.
    def tick
      hoy = @today_provider.call

      iniciadas = []
      @repo.por_iniciar(hoy).each do |periodo|
        actualizado = @repo.marcar_en_curso(periodo['id'])
        next if actualizado.nil? # ya no está PROGRAMADA: otro tick/instancia lo movió

        iniciadas << actualizado
        @publisher.publish_vacaciones_iniciadas(actualizado, email_de(actualizado['empleadoId']))
      end

      finalizadas = []
      @repo.por_finalizar(hoy).each do |periodo|
        actualizado = @repo.marcar_finalizada(periodo['id'])
        next if actualizado.nil? # ya no está EN_CURSO: nada que publicar

        finalizadas << actualizado
        @publisher.publish_vacaciones_finalizadas(actualizado, email_de(actualizado['empleadoId']))
      end

      if (iniciadas.size + finalizadas.size).positive?
        @logger.info(
          "[scheduler] transiciones: #{iniciadas.size} EN_CURSO, #{finalizadas.size} FINALIZADA (hoy=#{hoy.iso8601})"
        )
      end
      [iniciadas.size, finalizadas.size]
    end

    private

    # Email desnormalizado desde la réplica local; nil si el empleado no
    # llegó (el evento igual se publica, como con programadas).
    def email_de(empleado_id)
      empleado = @empleados.buscar(empleado_id)
      empleado && empleado['email']
    end
  end
end
