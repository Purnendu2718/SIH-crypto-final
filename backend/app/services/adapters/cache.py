"""In-memory Short-TTL Cache with Rate-Limit & Failure Resilience.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8.

Implements dual-TTL caching:
- 15-30s TTL for unconfirmed / low-confirmation transactions (< N confirmations).
- 300s TTL for settled / finalized blockchain transactions.
Graceful degradation: On live API error or HTTP 429 rate limit, serves the last cached
result with an explicit `is_stale=True` flag rather than crashing or silently substituting
fixture data without notice.
"""

import time
import logging
from typing import Optional, Tuple, Any, Dict, List
from app.config import settings

logger = logging.getLogger("sentinel.adapters.cache")


class CacheEntry:
    def __init__(self, data: Any, has_low_confirmation: bool):
        self.data = data
        self.has_low_confirmation = has_low_confirmation
        self.created_at = time.time()
        self.ttl = (
            settings.CACHE_TTL_PENDING
            if has_low_confirmation
            else settings.CACHE_TTL_SETTLED
        )

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl


class AdapterCache:
    """Singleton in-memory cache for live blockchain queries."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AdapterCache, cls).__new__(cls)
            cls._instance._store: Dict[str, CacheEntry] = {}
        return cls._instance

    def get(self, key: str) -> Optional[Tuple[Any, bool]]:
        """Retrieve cached entry.
        Returns:
            (data, is_stale) if key exists.
            None if key was never cached.
        """
        entry = self._store.get(key)
        if not entry:
            return None

        is_stale = entry.is_expired()
        return entry.data, is_stale

    def set(self, key: str, data: Any, has_low_confirmation: bool = False) -> None:
        """Cache data with appropriate TTL based on confirmation depth."""
        self._store[key] = CacheEntry(data=data, has_low_confirmation=has_low_confirmation)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()


# Global instance
adapter_cache = AdapterCache()
