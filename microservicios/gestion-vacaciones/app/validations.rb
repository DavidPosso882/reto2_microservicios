# frozen_string_literal: true

require 'date'

module Vacaciones
  # Pure domain validation logic for POST /vacaciones.
  # Returns an array of error hashes; empty means the request is valid.
  # Ordering is deterministic: fechaInicio, fechaFin, rango, empleado, solapamiento.
  class Validations
    Error = Struct.new(:message, :conflicto, keyword_init: true)

    def initialize(empleados_repo, vacaciones_repo, today_provider: -> { Date.today })
      @empleados = empleados_repo
      @vacaciones = vacaciones_repo
      @today_provider = today_provider
    end

    # attrs: { 'empleadoId' =>, 'fechaInicio' =>, 'fechaFin' => }
    def call(attrs)
      errors = []
      fecha_inicio = parse_date(attrs['fechaInicio'])
      fecha_fin = parse_date(attrs['fechaFin'])

      errors << Error.new(message: 'fechaInicio es obligatorio y debe tener formato YYYY-MM-DD') if fecha_inicio.nil?
      errors << Error.new(message: 'fechaFin es obligatorio y debe tener formato YYYY-MM-DD') if fecha_fin.nil?

      if fecha_inicio && fecha_fin && fecha_fin < fecha_inicio
        errors << Error.new(
          message: "fechaFin (#{attrs['fechaFin']}) debe ser igual o posterior a fechaInicio (#{attrs['fechaInicio']})"
        )
      end

      hoy = @today_provider.call
      if fecha_inicio && fecha_inicio < hoy
        errors << Error.new(
          message: "fechaInicio (#{attrs['fechaInicio']}) no puede ser anterior a la fecha actual (#{hoy.iso8601})"
        )
      end

      empleado_id = attrs['empleadoId']
      empleado = empleado_id && @empleados.buscar(empleado_id)
      if empleado_id.nil? || empleado_id.to_s.strip.empty?
        errors << Error.new(message: 'empleadoId es obligatorio')
      elsif empleado.nil?
        errors << Error.new(
          message: "El empleado '#{empleado_id}' no existe en la réplica local (aún no llegó el evento empleado.creado)"
        )
      elsif empleado['estado'] == 'RETIRADO'
        errors << Error.new(
          message: "El empleado '#{empleado_id}' está RETIRADO y no puede programar vacaciones"
        )
      end

      if fecha_inicio && fecha_fin && empleado && (conflicto = @vacaciones.buscar_solapamiento(empleado_id, fecha_inicio, fecha_fin))
        errors << Error.new(
          message: "El período se solapa con otro período del empleado '#{empleado_id}'",
          conflicto: conflicto
        )
      end

      errors
    end

    def self.parse_date(value)
      return nil if value.nil? || value.to_s.strip.empty?

      Date.parse(value.to_s)
    rescue Date::Error, ArgumentError
      nil
    end

    private

    def parse_date(value)
      self.class.parse_date(value)
    end
  end
end
