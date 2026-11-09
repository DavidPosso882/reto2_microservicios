# ── Stage: build (native extensions for pg) ─────────────────────────────────
FROM ruby:3.3-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY Gemfile ./
# No Gemfile.lock is committed to the repository (the host has no bundler).
# Bundler resolves from the Gemfile here and writes Gemfile.lock inside this
# stage, so the image build itself is the reproducible step. Frozen/deployment
# mode is deliberately NOT enabled: it requires a committed lockfile and makes
# the build fail with "The deployment setting requires a lockfile" (exit 16).
RUN bundle install --jobs 4

# ── Stage: runtime ──────────────────────────────────────────────────────────
FROM ruby:3.3-slim

# curl is required by the docker-compose healthcheck for this service
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /usr/local/bundle /usr/local/bundle
# Lockfile generated in the build stage: bundle exec at runtime resolves
# offline against the exact versions installed in this image.
COPY --from=build /app/Gemfile.lock ./Gemfile.lock
COPY Gemfile ./
COPY app ./app
COPY app.rb openapi.yaml ./
COPY tests ./tests

ENV RACK_ENV=production \
    BUNDLE_GEMFILE=/app/Gemfile

EXPOSE 8085

CMD ["ruby", "app.rb"]
