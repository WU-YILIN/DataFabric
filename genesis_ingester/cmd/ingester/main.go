package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
	"golang.org/x/time/rate"

	"github.com/genesis/ingester/internal/auth"
	"github.com/genesis/ingester/internal/config"
	"github.com/genesis/ingester/internal/handler"
	"github.com/genesis/ingester/internal/producer"
	"github.com/genesis/ingester/internal/ratelimit"
)

func main() {
	// ── Logger ────────────────────────────────────────────────────────────────
	logger, err := buildLogger()
	if err != nil {
		log.Fatalf("Failed to build logger: %v", err)
	}
	defer logger.Sync() //nolint:errcheck

	// ── Config ────────────────────────────────────────────────────────────────
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("Invalid configuration", zap.Error(err))
	}
	logger.Info("Genesis Ingestion Gateway starting",
		zap.String("listen_addr", cfg.ListenAddr),
		zap.String("kafka_topic", cfg.KafkaTopic),
	)

	// ── Redis ─────────────────────────────────────────────────────────────────
	rdb := redis.NewClient(&redis.Options{
		Addr:     cfg.RedisAddr,
		Password: cfg.RedisPassword,
		DB:       cfg.RedisDB,
	})
	if err = rdb.Ping(context.Background()).Err(); err != nil {
		logger.Warn("Redis ping failed — API key store will start empty", zap.Error(err))
	}

	// ── Auth KeyStore ─────────────────────────────────────────────────────────
	keyStore, err := auth.NewKeyStore(rdb, logger)
	if err != nil {
		logger.Fatal("Failed to initialize key store", zap.Error(err))
	}

	// ── Kafka Async Producer ──────────────────────────────────────────────────
	prod, err := producer.New(
		cfg.KafkaBrokers,
		cfg.KafkaTopic,
		cfg.ProducerQueueSize,
		cfg.ProducerBatchSize,
		cfg.ProducerFlushMs,
		logger,
	)
	if err != nil {
		logger.Fatal("Failed to create Kafka producer", zap.Error(err))
	}
	defer prod.Close()

	// ── Rate Limiter ──────────────────────────────────────────────────────────
	limiter := ratelimit.NewIPRateLimiter(
		rate.Limit(cfg.RateLimitPerSec),
		cfg.RateLimitBurst,
	)

	// ── HTTP Router ───────────────────────────────────────────────────────────
	mux := http.NewServeMux()

	// Public hot path — exposed to all clients (web, iOS, Android, backend services)
	ingestH := handler.NewIngestHandler(keyStore, prod, cfg.MaxBodyBytes, logger)
	mux.Handle("POST /v1/ingest",       ratelimit.Middleware(limiter)(ingestH))
	mux.Handle("POST /v1/ingest/batch", ratelimit.Middleware(limiter)(ingestH)) // alias

	// Liveness probe — used by Kubernetes / load balancer health checks
	mux.HandleFunc("GET /health", handler.HealthHandler())

	// Internal admin endpoints — should ONLY be reachable from the internal network / VPN
	adminH := handler.NewAdminHandler(keyStore, cfg.InternalAPIKey, logger)
	mux.HandleFunc("POST /admin/keys",   adminH.AddKeyHandler())
	mux.HandleFunc("DELETE /admin/keys", adminH.RemoveKeyHandler())

	// Global request logging middleware
	httpHandler := requestLogger(logger)(mux)

	// ── HTTP Server ───────────────────────────────────────────────────────────
	srv := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           httpHandler,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      5 * time.Second,
		IdleTimeout:       120 * time.Second, // Keep-Alive window
		ReadHeaderTimeout: 2 * time.Second,
		MaxHeaderBytes:    32 << 10, // 32 KB max headers
	}

	// Start listening in a goroutine so we can wait for a shutdown signal
	serverErr := make(chan error, 1)
	go func() {
		logger.Info(fmt.Sprintf("Listening on %s", cfg.ListenAddr))
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	// ── Graceful Shutdown ─────────────────────────────────────────────────────
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		logger.Info("Received shutdown signal", zap.String("signal", sig.String()))
	case err := <-serverErr:
		logger.Fatal("HTTP server error", zap.Error(err))
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		logger.Error("Graceful shutdown failed", zap.Error(err))
	}
	logger.Info("Gateway shut down cleanly")
}

// requestLogger logs method, path, status, and latency for every request.
func requestLogger(log *zap.Logger) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			rw := &responseWriter{ResponseWriter: w, status: http.StatusOK}
			next.ServeHTTP(rw, r)
			log.Info("request",
				zap.String("method", r.Method),
				zap.String("path", r.URL.Path),
				zap.Int("status", rw.status),
				zap.Duration("latency", time.Since(start)),
				zap.String("ip", r.RemoteAddr),
			)
		})
	}
}

type responseWriter struct {
	http.ResponseWriter
	status int
}

func (rw *responseWriter) WriteHeader(code int) {
	rw.status = code
	rw.ResponseWriter.WriteHeader(code)
}

// buildLogger returns a zap logger configured for the current environment.
// JSON format in production (LOG_FORMAT=json), coloured console otherwise.
func buildLogger() (*zap.Logger, error) {
	if os.Getenv("LOG_FORMAT") == "json" {
		return zap.NewProduction()
	}
	cfg := zap.NewDevelopmentConfig()
	cfg.EncoderConfig.EncodeLevel = zapcore.CapitalColorLevelEncoder
	return cfg.Build()
}
