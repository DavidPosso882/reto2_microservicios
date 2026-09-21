# ── Stage 1: build ──────────────────────────────────────────────────────────
FROM golang:1.26-alpine AS build

WORKDIR /src

# Cache de dependencias primero
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux \
    go build -trimpath -ldflags="-s -w" -o /out/perfiles-service ./cmd/perfiles-service

# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM alpine:3.22

# CA certs por si el entorno requiere TLS; wget (busybox) para el healthcheck.
RUN apk add --no-cache ca-certificates

WORKDIR /app
COPY --from=build /out/perfiles-service /app/perfiles-service
COPY openapi.yaml /app/openapi.yaml

EXPOSE 8083

CMD ["/app/perfiles-service"]
