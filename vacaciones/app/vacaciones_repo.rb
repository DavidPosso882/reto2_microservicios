# frozen_string_literal: true

require 'date'
require 'json'

module Vacaciones
  class VacacionesRepo
    def initialize(db)
      @db = db
    end

    def connection
      @db.connection
    end

    def todos(empleado_id: nil)
      if empleado_id
        rows = connection.exec_params(
          'SELECT * FROM vacaciones WHERE empleado_id = $1 ORDER BY fecha_creacion',
          [empleado_id]
        )
      else
        rows = connection.exec('SELECT * FROM vacaciones ORDER BY fecha_creacion')
      end
      rows.map { |r| from_row(r) }
    end

    def buscar(id)
      row = connection.exec_params('SELECT * FROM vacaciones WHERE id = $1', [id])
      row.ntuples.zero? ? nil : from_row(row[0])
    end

    # Overlap test: inclusive range intersection against another period of the
    # same employee in PROGRAMADA or EN_CURSO. Runs inside the caller transaction.
    def buscar_solapamiento(empleado_id, fecha_inicio, fecha_fin)
      row = connection.exec_params(
        <<~SQL,
          SELECT * FROM vacaciones
          WHERE empleado_id = $1
            AND estado IN ('PROGRAMADA', 'EN_CURSO')
            AND fecha_inicio <= $3::date
            AND fecha_fin >= $2::date
          LIMIT 1
        SQL
        [empleado_id, fecha_inicio.iso8601, fecha_fin.iso8601]
      )
      row.ntuples.zero? ? nil : from_row(row[0])
    end

    # Id generation + insert in ONE transaction; SELECT ... FOR UPDATE on the
    # latest row of the year serializes concurrent inserts for the same year.
    def crear(empleado_id:, fecha_inicio:, fecha_fin:, id_generator:, now_provider: -> { Time.now.utc })
      resultado = nil
      @db.with_transaction do |conn|
        nuevo_id = id_generator.next_id(conn)
        ahora = now_provider.call
        conn.exec_params(
          <<~SQL,
            INSERT INTO vacaciones (id, empleado_id, fecha_inicio, fecha_fin, estado, fecha_creacion)
            VALUES ($1, $2, $3::date, $4::date, 'PROGRAMADA', $5)
          SQL
          [nuevo_id, empleado_id, fecha_inicio.iso8601, fecha_fin.iso8601, ahora.iso8601]
        )
        resultado = {
          'id' => nuevo_id,
          'empleadoId' => empleado_id,
          'fechaInicio' => fecha_inicio.iso8601,
          'fechaFin' => fecha_fin.iso8601,
          'estado' => 'PROGRAMADA',
          'fechaCreacion' => ahora.iso8601
        }
      end
      resultado
    end

    def cancelar(id)
      row = connection.exec_params(
        "UPDATE vacaciones SET estado = 'CANCELADA' WHERE id = $1 AND fecha_inicio > CURRENT_DATE RETURNING *",
        [id]
      )
      row.ntuples.zero? ? nil : from_row(row[0])
    end

    # ── Reto 5: scheduler del ciclo de vida ──

    # Candidates to start: PROGRAMADA with fechaInicio <= today.
    def por_iniciar(hoy)
      rows = connection.exec_params(
        <<~SQL,
          SELECT * FROM vacaciones
          WHERE estado = 'PROGRAMADA' AND fecha_inicio <= $1::date
          ORDER BY fecha_inicio
        SQL
        [hoy.iso8601]
      )
      rows.map { |r| from_row(r) }
    end

    # Candidates to finish: EN_CURSO with fechaFin <= today (inclusive: the
    # demo strategy fechaInicio=hoy/fechaFin=hoy must complete the same day).
    def por_finalizar(hoy)
      rows = connection.exec_params(
        <<~SQL,
          SELECT * FROM vacaciones
          WHERE estado = 'EN_CURSO' AND fecha_fin <= $1::date
          ORDER BY fecha_fin
        SQL
        [hoy.iso8601]
      )
      rows.map { |r| from_row(r) }
    end

    # Conditional transition PROGRAMADA -> EN_CURSO. The WHERE clause on the
    # expected state makes the UPDATE idempotent: it only fires if the row is
    # still PROGRAMADA, so repeated ticks or racing instances cannot move a
    # CANCELADA/FINALIZADA row (or double-publish). Returns the updated period
    # or nil when zero rows matched.
    def marcar_en_curso(id)
      row = connection.exec_params(
        <<~SQL,
          UPDATE vacaciones SET estado = 'EN_CURSO'
          WHERE id = $1 AND estado = 'PROGRAMADA'
          RETURNING *
        SQL
        [id]
      )
      row.ntuples.zero? ? nil : from_row(row[0])
    end

    # Conditional transition EN_CURSO -> FINALIZADA (same idempotency rule).
    def marcar_finalizada(id)
      row = connection.exec_params(
        <<~SQL,
          UPDATE vacaciones SET estado = 'FINALIZADA'
          WHERE id = $1 AND estado = 'EN_CURSO'
          RETURNING *
        SQL
        [id]
      )
      row.ntuples.zero? ? nil : from_row(row[0])
    end

    # Baja por retiro: cancela los períodos PROGRAMADA con fecha_inicio
    # posterior a la fecha de retiro. No toca EN_CURSO (caso borde Reto 5:
    # el período en curso debe llegar a FINALIZADA sin reactivar la cuenta),
    # ni FINALIZADA/CANCELADA. Retorna los períodos cancelados.
    # Sin este paso, el scheduler pasaría a EN_CURSO vacaciones de un
    # retirado y publicaría vacaciones.iniciadas indebidas.
    def cancelar_futuras_por_retiro(empleado_id, fecha_retiro = nil)
      fecha_corte = self.class.parse_fecha_corte(fecha_retiro)
      if fecha_corte
        rows = connection.exec_params(
          <<~SQL,
            UPDATE vacaciones SET estado = 'CANCELADA'
            WHERE empleado_id = $1 AND estado = 'PROGRAMADA' AND fecha_inicio > $2::date
            RETURNING *
          SQL
          [empleado_id, fecha_corte.iso8601]
        )
      else
        rows = connection.exec_params(
          <<~SQL,
            UPDATE vacaciones SET estado = 'CANCELADA'
            WHERE empleado_id = $1 AND estado = 'PROGRAMADA' AND fecha_inicio > CURRENT_DATE
            RETURNING *
          SQL
          [empleado_id]
        )
      end
      rows.map { |r| from_row(r) }
    end

    def self.parse_fecha_corte(value)
      return nil if value.nil? || value.to_s.strip.empty?

      Date.parse(value.to_s)
    rescue Date::Error, ArgumentError
      nil
    end

    def from_row(row)
      {
        'id' => row['id'],
        'empleadoId' => row['empleado_id'],
        'fechaInicio' => parse_date_value(row['fecha_inicio']),
        'fechaFin' => parse_date_value(row['fecha_fin']),
        'estado' => row['estado'],
        'fechaCreacion' => parse_time_value(row['fecha_creacion'])
      }
    end

    private

    def parse_date_value(value)
      return nil if value.nil?

      value.is_a?(Date) ? value.iso8601 : Date.parse(value.to_s).iso8601
    end

    def parse_time_value(value)
      return nil if value.nil?

      value.is_a?(Time) ? value.utc.iso8601 : Time.parse(value.to_s).utc.iso8601
    end
  end
end
