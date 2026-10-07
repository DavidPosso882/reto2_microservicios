# frozen_string_literal: true

require 'fileutils'

module Minitest
  # Reporter mínimo de JUnit XML escrito con la librería estándar (no requiere
  # la gema minitest-junit). Se registra como plugin de Minitest siguiendo la
  # convención de nombre: al cargarse desde tests/support/minitest y añadirse
  # a Minitest.extensions, `Minitest.init_plugins` invoca plugin_junitxml_init.
  class JUnitXmlReporter < AbstractReporter
    def initialize(options = {})
      super()
      @results = []
      @reports_dir = ENV['VACACIONES_REPORTS_DIR'] ||
                     File.expand_path('../../../reports', __dir__)
    end

    def record(result)
      @results << result
    end

    def report
      FileUtils.mkdir_p(@reports_dir)
      path = File.join(@reports_dir, 'junit.xml')
      File.write(path, xml)
      warn "[junit] #{@results.size} tests -> #{path}"
    end

    private

    def xml
      suites = @results.group_by(&:klass).sort.to_h
      total_tests = @results.size
      total_failures = @results.sum { |r| kinds(r).count('failure') }
      total_errors = @results.sum { |r| kinds(r).count('error') }
      total_skipped = @results.sum { |r| kinds(r).count('skipped') }

      body = suites.map { |klass, results| suite_xml(klass, results) }.join
      <<~XML
        <?xml version="1.0" encoding="UTF-8"?>
        <testsuites name="vacaciones" tests="#{total_tests}" failures="#{total_failures}" errors="#{total_errors}" skipped="#{total_skipped}">
        #{body}</testsuites>
      XML
    end

    def suite_xml(klass, results)
      failures = results.sum { |r| kinds(r).count('failure') }
      errors = results.sum { |r| kinds(r).count('error') }
      skipped = results.sum { |r| kinds(r).count('skipped') }
      time = results.sum { |r| r.time.to_f }

      cases = results.map { |result| testcase_xml(result) }.join
      <<~XML
          <testsuite name="#{escape(klass)}" tests="#{results.size}" failures="#{failures}" errors="#{errors}" skipped="#{skipped}" time="#{format('%.6f', time)}">
        #{cases}  </testsuite>
      XML
    end

    def testcase_xml(result)
      attrs = %(classname="#{escape(result.klass)}" name="#{escape(result.name)}" time="#{format('%.6f', result.time.to_f)}")
      return "    <testcase #{attrs}/>\n" if kinds(result).empty?

      body = result.failures.map { |failure| failure_xml(failure) }.join
      "    <testcase #{attrs}>\n#{body}    </testcase>\n"
    end

    def failure_xml(failure)
      case kind(failure)
      when 'skipped'
        "      <skipped message=\"#{escape(failure.message)}\"/>\n"
      when 'error'
        "      <error message=\"#{escape(failure.message)}\" type=\"#{escape(failure.class.name)}\">#{escape(trace(failure))}</error>\n"
      else
        "      <failure message=\"#{escape(failure.message)}\" type=\"#{escape(failure.class.name)}\">#{escape(trace(failure))}</failure>\n"
      end
    end

    def kinds(result)
      result.failures.map { |failure| kind(failure) }
    end

    def kind(failure)
      return 'skipped' if Minitest.const_defined?(:Skip) && Minitest::Skip === failure
      return 'error' if Minitest.const_defined?(:UnexpectedError) && Minitest::UnexpectedError === failure

      'failure'
    end

    def trace(failure)
      backtrace = failure.respond_to?(:backtrace) ? failure.backtrace : nil
      Array(Minitest.filter_backtrace(backtrace)).join("\n")
    end

    def escape(text)
      text.to_s
          .gsub('&', '&amp;')
          .gsub('<', '&lt;')
          .gsub('>', '&gt;')
          .gsub('"', '&quot;')
          .gsub("'", '&apos;')
    end
  end

  def self.plugin_junitxml_init(options)
    reporter << JUnitXmlReporter.new(options)
  end
end
