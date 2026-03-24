package auth

import (
	"context"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
	"go.uber.org/zap"
)

const redisKeySetName = "datafabric:api_keys"

// KeyStore is a thread-safe in-memory cache of valid API keys,
// backed by a Redis set for durability and cross-node synchronization.
type KeyStore struct {
	mu     sync.RWMutex
	keys   map[string]struct{} // The hot in-memory lookup table
	rdb    *redis.Client
	logger *zap.Logger
}

// NewKeyStore creates a KeyStore and performs an initial sync from Redis.
func NewKeyStore(rdb *redis.Client, logger *zap.Logger) (*KeyStore, error) {
	ks := &KeyStore{
		keys:   make(map[string]struct{}),
		rdb:    rdb,
		logger: logger,
	}
	if err := ks.syncFromRedis(context.Background()); err != nil {
		// Non-fatal on startup — gateway can still run with an empty set
		logger.Warn("Initial key sync from Redis failed, starting with empty key set", zap.Error(err))
	}
	// Periodically re-sync to pick up changes pushed by DataFabric backend
	go ks.backgroundSync(30 * time.Second)
	return ks, nil
}

// IsValid returns true if the given key exists in the store (O(1), no I/O).
func (ks *KeyStore) IsValid(key string) bool {
	ks.mu.RLock()
	defer ks.mu.RUnlock()
	_, ok := ks.keys[key]
	return ok
}

// AddKey inserts a key into both Redis and the local cache.
// Called by the internal admin endpoint when DataFabric publishes a new Project.
func (ks *KeyStore) AddKey(ctx context.Context, key string) error {
	if err := ks.rdb.SAdd(ctx, redisKeySetName, key).Err(); err != nil {
		return err
	}
	ks.mu.Lock()
	ks.keys[key] = struct{}{}
	ks.mu.Unlock()
	return nil
}

// RemoveKey deletes a key from Redis and the local cache.
func (ks *KeyStore) RemoveKey(ctx context.Context, key string) error {
	if err := ks.rdb.SRem(ctx, redisKeySetName, key).Err(); err != nil {
		return err
	}
	ks.mu.Lock()
	delete(ks.keys, key)
	ks.mu.Unlock()
	return nil
}

// syncFromRedis fetches the full key set from Redis and replaces the local map.
func (ks *KeyStore) syncFromRedis(ctx context.Context) error {
	members, err := ks.rdb.SMembers(ctx, redisKeySetName).Result()
	if err != nil {
		return err
	}
	fresh := make(map[string]struct{}, len(members))
	for _, m := range members {
		fresh[m] = struct{}{}
	}
	ks.mu.Lock()
	ks.keys = fresh
	ks.mu.Unlock()
	ks.logger.Info("API key store synced", zap.Int("total_keys", len(fresh)))
	return nil
}

func (ks *KeyStore) backgroundSync(interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for range ticker.C {
		if err := ks.syncFromRedis(context.Background()); err != nil {
			ks.logger.Warn("Background key sync failed", zap.Error(err))
		}
	}
}
