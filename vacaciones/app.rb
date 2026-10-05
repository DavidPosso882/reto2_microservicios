# frozen_string_literal: true

require 'json'
require 'logger'
require 'sinatra/base'
require 'rack'
require 'rackup'
require 'rack/handler/puma'

require_relative 'app/config'
require_relative 'app/database'
require_relative 'app/id_generator'
require_relative 'app/validations'
require_relative 'app/empleados_locales_repo'
require_relative 'app/vacaciones_repo'
require_relative 'app/publisher'
require_relative 'app/empleados_consumer'
require_relative 'app/endpoints'

module Vacaciones
  class App < Sinatra::Base
    configure do
      set :root, File.expand_path(__dir__)
      set :show_exceptions, false
      set :raise_errors, false
    end

    before do
      content_type 'application/json'
      logger.info("#{request.request_method} #{request.path_info}")
    end

    def logger
      settings.logger
    end

    # ── Health & docs ─────────────────────────────────────────────────────────
    get '/health' do
      JSON.generate(status: 'ok', service: 'vacaciones-service')
    end

    get '/openapi.yaml' do
      content_type 'application/yaml'
      File.read(File.expand_path('openapi.yaml', __dir__))
    end

    # Swagger UI mínimo sin dependencias: CDN + spec relativa ./openapi.yaml.
    # Relativa a propósito: funciona directo y vía gateway
    # (/vacaciones/docs -> /docs upstream, ./openapi.yaml -> /vacaciones/openapi.yaml).
    get '/docs' do
      content_type 'text/html'
      <<~HTML
        <!DOCTYPE html>
        <html lang="es">
        <head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>vacaciones-service - Swagger UI</title>
        <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
        </head>
        <body><div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>window.onload=()=>{SwaggerUIBundle({url:"./openapi.yaml",dom_id:"#swagger-ui"})};</script>
        </body></html>
      HTML
    end

    # Misma página en /docs/ SIN redirect: un 302 con Location: /docs pierde
    # el prefijo /vacaciones vía gateway y el navegador termina en 404.
    get '/docs/' do
      content_type 'text/html'
      <<~HTML
        <!DOCTYPE html>
        <html lang="es">
        <head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>vacaciones-service - Swagger UI</title>
        <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"/>
        </head>
        <body><div id="swagger-ui"></div>
        <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script>window.onload=()=>{SwaggerUIBundle({url:"./openapi.yaml",dom_id:"#swagger-ui"})};</script>
        </body></html>
      HTML
    end

    # ── REST: vacaciones (delegates to Vacaciones::Endpoints) ─────────────────
    get '/vacaciones' do
      body, obj = endpoints.index(params['empleadoId'])
      status body
      JSON.generate(obj)
    end

    get '/vacaciones/:id' do
      body, obj = endpoints.show(params['id'])
      status body
      JSON.generate(obj)
    end

    post '/vacaciones' do
      body, obj = endpoints.create(parse_json_body)
      status body
      JSON.generate(obj)
    end

    delete '/vacaciones/:id' do
      body, obj = endpoints.destroy(params['id'])
      status body
      JSON.generate(obj)
    end

    error 500 do
      err = env['sinatra.error']
      logger.error("[error] #{err&.class}: #{err&.message}")
      JSON.generate(status: 500, error: 'Error interno del servicio')
    end

    private

    def endpoints
      settings.endpoints
    end

    def parse_json_body
      raw = request.body.read
      halt 400, JSON.generate(error: 'El cuerpo de la petición debe ser JSON válido') if raw.to_s.strip.empty?
      parsed = JSON.parse(raw)
      halt 400, JSON.generate(error: 'El cuerpo de la petición debe ser un objeto JSON') unless parsed.is_a?(Hash)
      parsed
    rescue JSON::ParserError
      halt 400, JSON.generate(error: 'El cuerpo de la petición debe ser JSON válido')
    end
  end

  # Bootstraps configuration, database, repos, publisher and consumer thread.
  class Boot
    def self.build(env = ENV)
      config = Config.new(env)
      logger = Logger.new($stdout)
      logger.level = Logger::INFO
      logger.formatter = proc { |_severity, _time, _prog, msg| "[vacaciones-service] #{msg}\n" }

      db = Database.new(config)
      db.ensure_schema

      empleados_repo = EmpleadosLocalesRepo.new(db)
      vacaciones_repo = VacacionesRepo.new(db)
      id_generator = IdGenerator.new
      validations = Validations.new(empleados_repo, vacaciones_repo)
      publisher = Publisher.new(config, logger)
      consumer = EmpleadosConsumer.new(db, empleados_repo, logger, config, vacaciones_repo)
      endpoints = Endpoints.new(
        empleados_repo: empleados_repo,
        vacaciones_repo: vacaciones_repo,
        id_generator: id_generator,
        validations: validations,
        publisher: publisher
      )

      # Sinatra 4 does not yield the app class inside `configure`, so set
      # the settings directly via the public class-level `set` method.
      App.set :config, config
      App.set :endpoints, endpoints
      App.set :logger, logger

      [App, consumer, logger, config]
    end

    def self.run!
      app, consumer, logger, config = build
      Thread.new { consumer.run }
      # Rack 3 removed Rack::Handler; puma registers Rackup::Handler::Puma
      # (the rackup gem must be loaded before rack/handler/puma).
      Rackup::Handler::Puma.run(app, Port: config.port, Host: '0.0.0.0')
    rescue StandardError => e
      logger&.error("fallo al arrancar: #{e.class}: #{e.message}")
      raise
    end
  end
end

Vacaciones::Boot.run! if $PROGRAM_NAME == __FILE__ && ENV['VACACIONES_BOOT'] != 'test'
