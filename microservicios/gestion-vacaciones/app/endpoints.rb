# frozen_string_literal: true

require 'date'
require 'json'

require_relative 'validations'

module Vacaciones
  # Request-handling logic for /vacaciones, decoupled from Sinatra so it can be
  # tested without a web server. Every method returns [http_status, body_object].
  # The Sinatra layer (app.rb) only serializes the body and sets the status.
  class Endpoints
    def initialize(empleados_repo:, vacaciones_repo:, id_generator:, validations:, publisher:,
                   today_provider: -> { Date.today })
      @empleados = empleados_repo
      @vacaciones = vacaciones_repo
      @id_generator = id_generator
      @validations = validations
      @publisher = publisher
      @today_provider = today_provider
    end

    # GET /vacaciones (optional empleadoId filter) → 200
    def index(empleado_id = nil)
      [200, @vacaciones.todos(empleado_id: empleado_id)]
    end

    # GET /vacaciones/{id} → 200 | 404
    def show(id)
      period = @vacaciones.buscar(id)
      return not_found(id) if period.nil?

      [200, period]
    end

    # POST /vacaciones → 201 | 400 (publish only after a successful save)
    def create(attrs)
      fecha_inicio = Validations.parse_date(attrs['fechaInicio'])
      fecha_fin = Validations.parse_date(attrs['fechaFin'])
      return [400, { 'error' => 'fechaInicio es obligatorio y debe tener formato YYYY-MM-DD' }] if fecha_inicio.nil?
      return [400, { 'error' => 'fechaFin es obligatorio y debe tener formato YYYY-MM-DD' }] if fecha_fin.nil?

      errors = @validations.call(attrs)
      return [400, error_body(errors.first)] unless errors.empty?

      resultado = @vacaciones.crear(
        empleado_id: attrs['empleadoId'],
        fecha_inicio: fecha_inicio,
        fecha_fin: fecha_fin,
        id_generator: @id_generator
      )

      empleado = @empleados.buscar(resultado['empleadoId'])
      @publisher.publish_vacaciones_programadas(resultado, empleado && empleado['email'])
      [201, resultado]
    end

    # DELETE /vacaciones/{id} → 200 (CANCELADA) | 400 (ya inició) | 404
    def destroy(id)
      period = @vacaciones.buscar(id)
      return not_found(id) if period.nil?

      inicio = Validations.parse_date(period['fechaInicio'])
      if inicio <= @today_provider.call
        return [400, { 'status' => 400, 'error' => "El período '#{id}' ya inició (fechaInicio #{period['fechaInicio']}) y no puede cancelarse" }]
      end

      cancelled = @vacaciones.cancelar(id)
      return not_found(id) if cancelled.nil?

      [200, cancelled]
    end

    private

    def error_body(error)
      body = { 'error' => error.message }
      body['conflicto'] = error.conflicto if error.conflicto
      body
    end

    def not_found(id)
      [404, { 'status' => 404, 'error' => "El período de vacaciones '#{id}' no existe" }]
    end
  end
end
