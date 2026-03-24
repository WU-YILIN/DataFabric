# ─── Build Stage ───────────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /app

# Install CGO dependencies required by confluent-kafka-go (librdkafka)
RUN apk add --no-cache gcc musl-dev librdkafka-dev pkgconf

COPY go.mod go.sum ./
RUN go mod download

COPY . .

# Build a statically-linked binary with CGO enabled (required for librdkafka bindings)
RUN CGO_ENABLED=1 go build -tags musl \
    -ldflags="-s -w" \
    -o /genesis-ingester \
    ./cmd/ingester

# ─── Run Stage ─────────────────────────────────────────────────────────────────
FROM alpine:3.19

# librdkafka runtime dependency
RUN apk add --no-cache librdkafka

# Run as non-root for better security posture
RUN addgroup -S ingester && adduser -S ingester -G ingester
USER ingester

COPY --from=builder /genesis-ingester /usr/local/bin/genesis-ingester

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:8080/health || exit 1

ENTRYPOINT ["genesis-ingester"]
