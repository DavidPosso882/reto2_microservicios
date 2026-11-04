# frozen_string_literal: true

require 'json'

module Vacaciones
  # Local replica of empleados, fed exclusively by RabbitMQ events
  # (opción b: réplica local por eventos, sin llamadas REST salientes).
  class EmpleadosLocalesRepo
    def initialize(db)
      @db = db
    end

    def buscar(empleado_id)
      row = @db.connection.exec_params(
        'SELECT empleado_id, email, nombre, estado, actualizado_en FROM empleados_locales WHERE empleado_id = $1',
        [empleado_id]
      )
      row.ntuples.zero? ? nil : row[0]
    end

    # empleado.creado (y empleado.actualizado si llegara): upsert con el estado del evento.
    def upsert(data)
      @db.connection.exec_params(
        <<~SQL,
          INSERT INTO empleados_locales (empleado_id, email, nombre, estado, actualizado_en)
          VALUES ($1, $2, $3, $4, now())
          ON CONFLICT (empleado_id) DO UPDATE SET
            email = EXCLUDED.email,
            nombre = EXCLUDED.nombre,
            estado = EXCLUDED.estado,
            actualizado_en = now()
        SQL
        [data['id'], data['email'].to_s, data['nombre'].to_s, data['estado'].to_s]
      )
    end

    # empleado.retirado: baja lógica (los períodos PROGRAMADA se conservan para auditoría).
    def marcar_retirado(data)
      @db.connection.exec_params(
        <<~SQL,
          INSERT INTO empleados_locales (empleado_id, email, nombre, estado, actualizado_en)
          VALUES ($1, $2, $3, 'RETIRADO', now())
          ON CONFLICT (empleado_id) DO UPDATE SET
            email = EXCLUDED.email,
            nombre = EXCLUDED.nombre,
            estado = 'RETIRADO',
            actualizado_en = now()
        SQL
        [data['id'], data['email'].to_s, data['nombre'].to_s]
      )
    end
  end
end
