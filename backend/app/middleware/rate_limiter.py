"""In-Memory Sliding-Window Rate Limiter Middleware for FastAPI.
Protects public endpoints (auth, unified search, quick-trace) against brute-force
and denial-of-service attacks.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 9 Hardening.
"""

import time
import threading
from typing import Dict, List, Tuple
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class RateLimiter:
    """Thread-safe sliding-window in-memory rate limiter."""

    def __init__(self):
        self._lock = threading.Lock()
        # Storage: {ip: [(timestamp, endpoint_key)]}
        self._requests: Dict[str, List[Tuple[float, str]]] = {}
        self._last_cleanup = time.time()

        # Endpoint Tier Configuration: (path_prefix, limit, window_seconds)
        self.tiers = [
            # High security: Login & Signup brute-force protection (10 req / 60s)
            ("/api/auth/login", 10, 60),
            ("/api/auth/signup", 10, 60),
            # Medium security: Search and Quick-Trace abuse protection (30 req / 60s)
            ("/api/v1/search", 30, 60),
            ("/api/search", 30, 60),
            ("/api/analysis/quick-trace", 30, 60),
            # Default fallback tier (120 req / 60s)
            ("*", 120, 60),
        ]

    def _get_tier(self, path: str) -> Tuple[str, int, int]:
        for prefix, limit, window in self.tiers:
            if prefix != "*" and path.startswith(prefix):
                return prefix, limit, window
        return "*", 120, 60

    def _clean_stale(self, now: float):
        """Prune timestamps older than 120 seconds to prevent memory accumulation."""
        if now - self._last_cleanup < 60:
            return
        cutoff = now - 120
        keys_to_remove = []
        for ip, timestamps in self._requests.items():
            fresh = [t for t in timestamps if t[0] > cutoff]
            if fresh:
                self._requests[ip] = fresh
            else:
                keys_to_remove.append(ip)
        for k in keys_to_remove:
            self._requests.pop(k, None)
        self._last_cleanup = now

    def is_allowed(self, ip: str, path: str) -> Tuple[bool, int, int, int]:
        """Check if request is permitted under sliding window.
        Returns: (allowed, remaining, limit, retry_after)
        """
        now = time.time()
        tier_key, limit, window = self._get_tier(path)

        with self._lock:
            self._clean_stale(now)
            user_requests = self._requests.setdefault(ip, [])

            # Filter for requests within the tier window matching this tier
            window_start = now - window
            recent = [t for t in user_requests if t[0] > window_start and t[1] == tier_key]

            if len(recent) >= limit:
                # Calculate remaining seconds until the oldest request leaves the window
                oldest = min(t[0] for t in recent)
                retry_after = max(1, int(window - (now - oldest)))
                return False, 0, limit, retry_after

            # Record this request
            user_requests.append((now, tier_key))
            remaining = limit - (len(recent) + 1)
            return True, remaining, limit, 0

    def reset(self):
        """Clear all rate limit records (used in tests)."""
        with self._lock:
            self._requests.clear()


limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware enforcing client rate limits."""

    async def dispatch(self, request: Request, call_next):
        # Allow disabling rate limiting in test or air-gapped environments
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return await call_next(request)

        # Skip health check and websocket paths from HTTP rate limiter
        path = request.url.path
        if path in ("/api/health", "/docs", "/openapi.json", "/redoc") or path.startswith("/api/ws/"):
            return await call_next(request)

        # Resolve client IP (support Nginx reverse proxy headers)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "127.0.0.1")

        allowed, remaining, limit, retry_after = limiter.is_allowed(client_ip, path)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Too many requests to '{path}'. Rate limit is {limit} requests per minute. Please retry in {retry_after} seconds.",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after)),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
