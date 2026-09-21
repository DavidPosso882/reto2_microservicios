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
