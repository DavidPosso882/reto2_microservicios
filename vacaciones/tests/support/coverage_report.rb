# frozen_string_literal: true

require 'coverage'
require 'fileutils'
require 'json'
require 'time'

# Reporte de cobertura de la app de vacaciones usando solo la librería estándar
# (Coverage), sin SimpleCov. Este entorno no tiene el ejecutable `bundle`, así
# que el runner produce igualmente reports/coverage/{coverage.json,index.html}.
module VacacionesCoverage
  APP_DIR = File.expand_path('../../app', __dir__)

  module_function

  # Escribe el reporte y devuelve el hash de resumen.
  def write_report(reports_dir)
    files = collect(Coverage.result)
    summary = summarize(files)
    out_dir = File.join(reports_dir, 'coverage')
    FileUtils.mkdir_p(out_dir)

    payload = {
      'generated_at' => Time.now.utc.iso8601,
      'tool' => 'coverage (stdlib de Ruby)',
      'scope' => APP_DIR,
      'summary' => summary,
      'files' => files
    }
    File.write(File.join(out_dir, 'coverage.json'), JSON.pretty_generate(payload))
    File.write(File.join(out_dir, 'index.html'), html(summary, files))

    warn format(
      '[coverage] lineas %<line>s%% (%<covered>s/%<total>s), ramas %<branch>s%% -> %<path>s',
      line: summary['line_coverage_percent'],
      covered: summary['lines_covered'],
      total: summary['lines_total'],
      branch: summary['branch_coverage_percent'],
      path: File.join(out_dir, 'index.html')
    )
    summary
  end

  def collect(results)
    results
      .select { |path, _data| path.start_with?("#{APP_DIR}/") && path.end_with?('.rb') }
      .sort
      .to_h do |path, data|
        lines = data[:lines] || []
        relevant = lines.count { |count| !count.nil? }
        covered = lines.count { |count| !count.nil? && count.positive? }
        branches = branch_counts(data[:branches] || {})

        [path.delete_prefix("#{APP_DIR}/"), {
          'lines_total' => relevant,
          'lines_covered' => covered,
          'line_coverage_percent' => percent(covered, relevant),
          'branches_total' => branches[:total],
          'branches_covered' => branches[:covered],
          'branch_coverage_percent' => percent(branches[:covered], branches[:total])
        }]
      end
  end

  def summarize(files)
    lines_total = files.sum { |_name, data| data['lines_total'] }
    lines_covered = files.sum { |_name, data| data['lines_covered'] }
    branches_total = files.sum { |_name, data| data['branches_total'] }
    branches_covered = files.sum { |_name, data| data['branches_covered'] }

    {
      'files' => files.size,
      'lines_total' => lines_total,
      'lines_covered' => lines_covered,
      'line_coverage_percent' => percent(lines_covered, lines_total),
      'branches_total' => branches_total,
      'branches_covered' => branches_covered,
      'branch_coverage_percent' => percent(branches_covered, branches_total)
    }
  end

  def branch_counts(branches)
    total = 0
    covered = 0
    branches.each_value do |arms|
      arms.each_value do |count|
        total += 1
        covered += 1 if count.positive?
      end
    end
    { total: total, covered: covered }
  end

  def percent(covered, total)
    return 100.0 if total.zero?

    ((covered * 100.0) / total).round(2)
  end

  def html(summary, files)
    rows = files.map do |name, data|
      <<~ROW
        <tr><td>#{name}</td><td>#{data['lines_covered']}/#{data['lines_total']}</td><td>#{data['line_coverage_percent']}%</td><td>#{data['branches_covered']}/#{data['branches_total']}</td><td>#{data['branch_coverage_percent']}%</td></tr>
      ROW
    end.join

    <<~HTML
      <!DOCTYPE html>
      <html lang="es">
      <head><meta charset="utf-8"><title>Cobertura vacaciones (stdlib)</title></head>
      <body>
        <h1>Cobertura vacaciones</h1>
        <p><strong>Lineas: #{summary['line_coverage_percent']}% (#{summary['lines_covered']}/#{summary['lines_total']})</strong>
           &mdash; Ramas: #{summary['branch_coverage_percent']}% (#{summary['branches_covered']}/#{summary['branches_total']})</p>
        <table border="1" cellpadding="4">
          <thead><tr><th>Archivo</th><th>Lineas</th><th>% Lineas</th><th>Ramas</th><th>% Ramas</th></tr></thead>
          <tbody>#{rows}</tbody>
        </table>
      </body>
      </html>
    HTML
  end
end
