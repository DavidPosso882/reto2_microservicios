# frozen_string_literal: true

module Vacaciones
  # Generates server-side vacation ids with format V-AAAA-NNNN.
  # The sequential part resets per year and is resolved with MAX+1
  # inside the same transaction as the INSERT (SELECT ... FOR UPDATE
  # on the conflicting candidate row serializes concurrent inserts).
  class IdGenerator
    FORMAT = /\AV-\d{4}-\d{4}\z/.freeze

    def initialize(clock: -> { Date.today })
      @clock = clock
    end

    def next_id(conn)
      year = @clock.call.year
      pattern = "V-#{year}-%"
      row = conn.exec_params(
        'SELECT id FROM vacaciones WHERE id LIKE $1 ORDER BY id DESC LIMIT 1 FOR UPDATE',
        [pattern]
      )
      tuples = row.respond_to?(:ntuples) ? row.ntuples : row.length
      last_seq = tuples.zero? ? 0 : row[0]['id'].split('-').last.to_i
      format('V-%04d-%04d', year, last_seq + 1)
    end

    def self.valid?(id)
      id.is_a?(String) && id.match?(FORMAT)
    end
  end
end
