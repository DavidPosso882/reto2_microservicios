# frozen_string_literal: true

# Configuration from environment variables with local defaults.
module Vacaciones
  class Config
    attr_reader :port, :db_host, :db_port, :db_name, :db_user, :db_password,
                :rabbitmq_host, :rabbitmq_port, :rabbitmq_user, :rabbitmq_password

    def initialize(env = ENV)
      @port = env.fetch('PORT', '8085').to_i
      @db_host = env.fetch('DB_HOST', 'localhost')
      @db_port = (env.fetch('DB_PORT', '5432') || '5432').to_i
      @db_name = env.fetch('DB_NAME', 'vacaciones')
      @db_user = env.fetch('DB_USER', 'postgres')
      @db_password = env.fetch('DB_PASSWORD', 'postgres')
      @rabbitmq_host = env.fetch('RABBITMQ_HOST', 'localhost')
      @rabbitmq_port = (env.fetch('RABBITMQ_PORT', '5672') || '5672').to_i
      @rabbitmq_user = env.fetch('RABBITMQ_USER', 'guest')
      @rabbitmq_password = env.fetch('RABBITMQ_PASSWORD', 'guest')
    end
  end
end
