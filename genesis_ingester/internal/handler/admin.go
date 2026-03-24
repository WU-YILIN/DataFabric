package handler

import (
	"context"
	"encoding/json"
	"net/http"

	"go.uber.org/zap"

	"github.com/genesis/ingester/internal/auth"
)

// AdminHandler exposes internal management endpoints called by the DataFabric backend.
// These are NOT exposed to the public internet — they should be protected by firewall / VPN.
type AdminHandler struct {
	keyStore       *auth.KeyStore
	internalAPIKey string // Pre-shared secret between gateway and DataFabric
	logger         *zap.Logger
}

func NewAdminHandler(ks *auth.KeyStore, internalAPIKey string, logger *zap.Logger) *AdminHandler {
	return &AdminHandler{keyStore: ks, internalAPIKey: internalAPIKey, logger: logger}
}

type keyPayload struct {
	Key string `json:"key"`
}

// AddKeyHandler handles POST /admin/keys — registers a new project API key.
func (a *AdminHandler) AddKeyHandler() http.HandlerFunc {
	return a.withAdminAuth(func(w http.ResponseWriter, r *http.Request) {
		var p keyPayload
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil || p.Key == "" {
			http.Error(w, `{"error":"invalid payload"}`, http.StatusBadRequest)
			return
		}
		if err := a.keyStore.AddKey(context.Background(), p.Key); err != nil {
			a.logger.Error("Failed to add key", zap.Error(err))
			http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
			return
		}
		a.logger.Info("API key added", zap.String("key_prefix", p.Key[:min(8, len(p.Key))]))
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
}

// RemoveKeyHandler handles DELETE /admin/keys — revokes a project API key.
func (a *AdminHandler) RemoveKeyHandler() http.HandlerFunc {
	return a.withAdminAuth(func(w http.ResponseWriter, r *http.Request) {
		var p keyPayload
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil || p.Key == "" {
			http.Error(w, `{"error":"invalid payload"}`, http.StatusBadRequest)
			return
		}
		if err := a.keyStore.RemoveKey(context.Background(), p.Key); err != nil {
			a.logger.Error("Failed to remove key", zap.Error(err))
			http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
			return
		}
		a.logger.Info("API key removed", zap.String("key_prefix", p.Key[:min(8, len(p.Key))]))
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
}

// HealthHandler handles GET /health — shallow liveness probe.
func HealthHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}
}

// withAdminAuth wraps a handler with a check for the internal API key (X-Internal-Key header).
func (a *AdminHandler) withAdminAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Key") != a.internalAPIKey {
			http.Error(w, `{"error":"forbidden"}`, http.StatusForbidden)
			return
		}
		next(w, r)
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
