package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config holds all runtime configuration for the ingestion gateway.
type Config struct {
	// HTTP Server
	ListenAddr string // e.g. ":8080"

	// Kafka
	KafkaBrokers string // e.g. "localhost:9092"
	KafkaTopic   string // e.g. "ods_raw_events"

	// Redis — used for the in-memory API key cache
	RedisAddr     string // e.g. "localhost:6379"
	RedisPassword string
	RedisDB       int

	// Security
	MaxBodyBytes    int64  // Max payload size in bytes (default 512KB)
	RateLimitPerSec int    // Requests per second per IP (token bucket)
	RateLimitBurst  int    // Burst size
	InternalAPIKey  string // Secret key used by DataFabric to push key updates

	// Async producer buffer
	ProducerQueueSize int // Size of the in-process async channel
	ProducerBatchSize int // How many messages to batch before flushing to Kafka
	ProducerFlushMs   int // Max time (ms) to wait before flushing a partial batch
}

// Load reads config from environment variables with sensible defaults.
func Load() (*Config, error) {
	cfg := &Config{
		ListenAddr:        getEnv("LISTEN_ADDR", ":8080"),
		KafkaBrokers:      getEnv("KAFKA_BROKERS", "localhost:9092"),
		KafkaTopic:        getEnv("KAFKA_TOPIC", "ods_raw_events"),
		RedisAddr:         getEnv("REDIS_ADDR", "localhost:6379"),
		RedisPassword:     getEnv("REDIS_PASSWORD", ""),
		RedisDB:           getEnvInt("REDIS_DB", 0),
		MaxBodyBytes:      int64(getEnvInt("MAX_BODY_BYTES", 524288)), // 512 KB
		RateLimitPerSec:   getEnvInt("RATE_LIMIT_PER_SEC", 200),
		RateLimitBurst:    getEnvInt("RATE_LIMIT_BURST", 500),
		InternalAPIKey:    getEnv("INTERNAL_API_KEY", "change-me-in-production"),
		ProducerQueueSize: getEnvInt("PRODUCER_QUEUE_SIZE", 10000),
		ProducerBatchSize: getEnvInt("PRODUCER_BATCH_SIZE", 1000),
		ProducerFlushMs:   getEnvInt("PRODUCER_FLUSH_MS", 500),
	}

	if cfg.KafkaBrokers == "" {
		return nil, fmt.Errorf("KAFKA_BROKERS must be set")
	}
	return cfg, nil
}

func getEnv(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok && strings.TrimSpace(v) != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v, ok := os.LookupEnv(key); ok {
		if i, err := strconv.Atoi(v); err == nil {
			return i
		}
	}
	return fallback
}
