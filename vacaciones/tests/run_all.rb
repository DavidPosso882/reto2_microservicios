# frozen_string_literal: true

# Runner único de la suite de vacaciones (Reto 6, Punto 1).
#
# - Ejecuta todos los archivos tests/*_test.rb en un solo proceso.
# - Escribe dos reportes con la librería estándar, sin requerir bundle install:
#     reports/junit.xml            (plugin local minitest/*_plugin.rb)
#     reports/coverage/index.html  (Coverage de la stdlib)
#
# Uso (desde vacaciones/):
#   ruby tests/run_all.rb
#
# Nota: el Gemfile declara minitest-junit y simplecov para entornos con
# bundler; aquí no hay ejecutable `bundle`, así que se usan los equivalentes
# de la stdlib y la suite sigue corriendo igual con `ruby tests/<archivo>.rb`.

require 'coverage'
require 'fileutils'

REPORTS_DIR = ENV['VACACIONES_REPORTS_DIR'] || File.expand_path('../reports', __dir__)
FileUtils.mkdir_p(REPORTS_DIR)

# Debe arrancar antes de cargar los archivos de app/ para registrar sus líneas.
Coverage.start(lines: true, branches: true)

$LOAD_PATH.unshift File.expand_path('support', __dir__)

require 'minitest'
require 'minitest/autorun'

require_relative 'support/minitest/junitxml_plugin'
Minitest.extensions << 'junitxml' unless Minitest.extensions.include?('junitxml')

require_relative 'support/coverage_report'

Dir[File.expand_path('*_test.rb', __dir__)].sort.each { |file| require file }

Minitest.after_run do
  VacacionesCoverage.write_report(REPORTS_DIR)
end
