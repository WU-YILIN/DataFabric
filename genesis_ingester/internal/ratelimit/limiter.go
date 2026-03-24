package ratelimit

import (
	"net"
	"net/http"
	"sync"

	"golang.org/x/time/rate"
)

// IPRateLimiter implements a per-IP token-bucket rate limiter.
// It is safe for concurrent use from multiple goroutines.
type IPRateLimiter struct {
	mu       sync.Mutex
	limiters map[string]*rate.Limiter
	r        rate.Limit // tokens per second
	b        int        // burst capacity
}

// NewIPRateLimiter creates a new limiter allowing r requests/sec with burst b.
func NewIPRateLimiter(r rate.Limit, b int) *IPRateLimiter {
	return &IPRateLimiter{
		limiters: make(map[string]*rate.Limiter),
		r:        r,
		b:        b,
	}
}

// Allow reports whether the request from the given IP should be allowed.
func (i *IPRateLimiter) Allow(ip string) bool {
	i.mu.Lock()
	lim, exists := i.limiters[ip]
	if !exists {
		lim = rate.NewLimiter(i.r, i.b)
		i.limiters[ip] = lim
	}
	i.mu.Unlock()
	return lim.Allow()
}

// ExtractIP returns just the host portion from a RemoteAddr string.
func ExtractIP(remoteAddr string) string {
	ip, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		return remoteAddr // fallback for unusual formats
	}
	return ip
}

// Middleware returns an HTTP middleware that applies per-IP rate limiting.
// Requests that exceed the limit get a 429 Too Many Requests response.
func Middleware(lim *IPRateLimiter) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ip := ExtractIP(r.RemoteAddr)
			// Prefer X-Forwarded-For when behind a load balancer
			if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
				ip = xff
			}
			if !lim.Allow(ip) {
				http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
