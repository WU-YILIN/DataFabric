package handler

import (
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/google/uuid"
	"go.uber.org/zap"

	"github.com/genesis/ingester/internal/auth"
	"github.com/genesis/ingester/internal/producer"
)

// IngestHandler handles the hot ingest path.
// It is intentionally lean: authenticate -> decompress -> enrich -> enqueue -> 200 OK.
type IngestHandler struct {
	keyStore     *auth.KeyStore
	producer     *producer.AsyncProducer
	maxBodyBytes int64
	logger       *zap.Logger
}

// ingestEnvelope is the minimal metadata we prepend to every raw payload.
// The rest of the JSON body is stored verbatim for Schema-on-Read to handle.
type ingestEnvelope struct {
	UUID        string          `json:"_uuid"`
	ServerTime  string          `json:"_server_time"`
	ProjectKey  string          `json:"_project_key"`
	RemoteIP    string          `json:"_remote_ip"`
	RawPayload  json.RawMessage `json:"raw_payload"` // verbatim — no unmarshal
}

// NewIngestHandler creates a ready-to-use IngestHandler.
func NewIngestHandler(
	ks *auth.KeyStore,
	p *producer.AsyncProducer,
	maxBodyBytes int64,
	logger *zap.Logger,
) *IngestHandler {
	return &IngestHandler{
		keyStore:     ks,
		producer:     p,
		maxBodyBytes: maxBodyBytes,
		logger:       logger,
	}
}

// ServeHTTP is the core of the hot path:
//  1. Auth  — O(1) in-memory map lookup
//  2. Limit — body size guard
//  3. Read  — decompress if gzip
//  4. Wrap  — prepend server-side metadata (UUID, timestamp, IP)
//  5. Enqueue — non-blocking channel push
//  6. Return 204 No Content immediately
func (h *IngestHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	// --- 1. Auth ---
	apiKey := r.Header.Get("X-Project-Key")
	if apiKey == "" || !h.keyStore.IsValid(apiKey) {
		http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
		return
	}

	// --- 2. Body-size guard (max 512 KB by default) ---
	r.Body = http.MaxBytesReader(w, r.Body, h.maxBodyBytes)

	// --- 3. Read + gzip decompression ---
	body, err := h.readBody(r)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err.Error()), http.StatusRequestEntityTooLarge)
		return
	}
	if len(body) == 0 {
		http.Error(w, `{"error":"empty body"}`, http.StatusBadRequest)
		return
	}

	// Basic JSON sanity check — must start with { or [
	firstByte := body[0]
	if firstByte != '{' && firstByte != '[' {
		http.Error(w, `{"error":"body must be JSON object or array"}`, http.StatusBadRequest)
		return
	}

	// --- 4. Wrap with server-side metadata ---
	// We do NOT unmarshal the payload — we store it as json.RawMessage to preserve the original structure exactly.
	env := ingestEnvelope{
		UUID:       uuid.New().String(),
		ServerTime: time.Now().UTC().Format(time.RFC3339Nano),
		ProjectKey: apiKey,
		RemoteIP:   extractIP(r),
		RawPayload: json.RawMessage(body),
	}
	wrapped, err := json.Marshal(env)
	if err != nil {
		h.logger.Error("Failed to marshal envelope", zap.Error(err))
		http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
		return
	}

	// --- 5. Non-blocking enqueue → Kafka (fire-and-forget) ---
	if !h.producer.Enqueue(wrapped) {
		// Back-pressure path: queue is full, return 503
		http.Error(w, `{"error":"service busy, retry later"}`, http.StatusServiceUnavailable)
		return
	}

	// --- 6. Return immediately — do not make the client wait for Kafka ACK ---
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusNoContent) // 204 No Content
}

// readBody reads the request body, transparently decompressing gzip if needed.
func (h *IngestHandler) readBody(r *http.Request) ([]byte, error) {
	var reader io.Reader = r.Body
	if r.Header.Get("Content-Encoding") == "gzip" {
		gz, err := gzip.NewReader(r.Body)
		if err != nil {
			return nil, fmt.Errorf("invalid gzip body: %w", err)
		}
		defer gz.Close()
		reader = gz
	}
	return io.ReadAll(reader)
}

func extractIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		return xff
	}
	return r.RemoteAddr
}
