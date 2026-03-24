# Genesis Ingestion Gateway (`genesis_ingester`)

A high-performance, low-latency HTTP ingestion gateway written in **Go**.

It sits in front of your Kafka cluster and is the **only entry point** for all tracking events from Web, iOS, Android, and backend services.

## Design Philosophy

| Goal | How |
|---|---|
| **Ultra-high throughput** | Go goroutines + non-blocking async Kafka producer |
| **Low latency** | Returns HTTP 204 before waiting for Kafka ACK |
| **Zero data loss** | Raw payload stored verbatim — no field pruning |
| **Security** | In-memory API key lookup + per-IP token bucket + body size guard |
| **Hot key management** | Keys synced from Redis — no gateway restart required |
| **Multi-platform** | Accepts any valid JSON from any HTTP client |

## Architecture

```
Client (iOS / Web / Backend)
         ↓  HTTP POST /v1/ingest  (Gzip compressed)
[Load Balancer / Nginx]  ←─ TLS termination here
         ↓  plain HTTP
[Genesis Ingester (Go)]
  1. API Key auth     (O(1) in-memory map)
  2. Body size guard  (≤ 512 KB)
  3. IP rate limit    (token bucket, 200 req/s per IP)
  4. Gzip decompress  (transparent)
  5. Wrap metadata    (UUID, server_time, project_key)
  6. Enqueue          (non-blocking Go channel)
  7. Return 204 OK
         ↓  async batch (LZ4 compressed)
[Kafka Topic: ods_raw_events]
         ↓
[DataFabric Schema-on-Read layer]
```

## Project Structure

```
genesis_ingester/
├── cmd/ingester/main.go          # Entry point + HTTP server assembly
├── internal/
│   ├── auth/keystore.go          # In-memory API key store (Redis-backed)
│   ├── config/config.go          # Env-var configuration
│   ├── handler/
│   │   ├── ingest.go             # Hot path HTTP handler
│   │   └── admin.go              # Internal key management endpoints
│   ├── producer/kafka_producer.go# Async Kafka producer (LZ4, micro-batch)
│   └── ratelimit/limiter.go      # Per-IP token bucket middleware
├── Dockerfile                    # Multi-stage build
└── .env.example                  # Configuration reference
```

## Quick Start

### Prerequisites
- Go 1.22+
- `librdkafka` development headers (`brew install librdkafka` / `apt install librdkafka-dev`)
- A running Kafka instance
- A running Redis instance

### Run locally

```bash
cd genesis_ingester

# Copy and edit config
cp .env.example .env

# Download dependencies
go mod download

# Run the gateway
go run ./cmd/ingester
```

### Build Docker image

```bash
docker build -t genesis-ingester:latest .

docker run -d \
  --env-file .env \
  -p 8080:8080 \
  genesis-ingester:latest
```

## API endpoints

### `POST /v1/ingest` — Send events (public)
- **Header**: `X-Project-Key: <your-api-key>`
- **Header**: `Content-Encoding: gzip` *(optional but recommended)*
- **Body**: Any valid JSON object `{}` or array `[...]`
- **Response**: `204 No Content` on success

**Example (single event):**
```bash
curl -X POST http://localhost:8080/v1/ingest \
  -H "X-Project-Key: my-api-key" \
  -H "Content-Type: application/json" \
  -d '{"event":"checkout","user_id":"u123","zhifu_jine":"99.9","is_vip":1}'
```

**Example (micro-batch, gzip compressed):**
```bash
echo '[{"event":"click"},{"event":"view"}]' | \
  gzip | \
  curl -X POST http://localhost:8080/v1/ingest \
    -H "X-Project-Key: my-api-key" \
    -H "Content-Encoding: gzip" \
    --data-binary @-
```

### `GET /health` — Liveness probe
Returns `{"status":"ok"}` with `200 OK`.

### `POST /admin/keys` — Register a new API key *(internal)*
- **Header**: `X-Internal-Key: <INTERNAL_API_KEY from env>`
- **Body**: `{"key":"new-project-key"}`

### `DELETE /admin/keys` — Revoke an API key *(internal)*
- **Header**: `X-Internal-Key: <INTERNAL_API_KEY from env>`
- **Body**: `{"key":"project-key-to-revoke"}`

> ⚠️ Admin endpoints must NOT be exposed to the public internet. Restrict via firewall/VPN.

## Kafka Message Format

Every message written to Kafka is a JSON envelope:

```json
{
  "_uuid": "550e8400-e29b-41d4-a716-446655440000",
  "_server_time": "2026-03-01T09:00:00.123456789Z",
  "_project_key": "my-api-key",
  "_remote_ip": "203.0.113.5",
  "raw_payload": { ...original untouched payload... }
}
```

The `raw_payload` is stored as-is. The DataFabric mapping engine handles field extraction and type coercion at query time (Schema-on-Read).
