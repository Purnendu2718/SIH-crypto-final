"""Base provider adapter architecture with SSRF protection, caching, retries, and rate limiting.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import asyncio
import os
import time
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

# In-memory TTL cache: (cache_key) -> (expiry_time, cached_data)
_PROVIDER_CACHE: Dict[str, Tuple[float, Any]] = {}
_CACHE_LOCK = asyncio.Lock()
_CACHE_TTL_SECONDS = 60.0

# Fixed Allowlist of permitted external provider hostnames (SSRF protection)
ALLOWED_HOSTS: Set[str] = {
    "mempool.space",
    "blockstream.info",
    "api.trongrid.io",
    "api.mainnet-beta.solana.com",
    "s1.ripple.com",
    "xrplcluster.com",
    "horizon.stellar.org",
    "ethereum-rpc.publicnode.com",
    "eth.llamarpc.com",
    "cloudflare-eth.com",
    "polygon-rpc.com",
    "arb1.arbitrum.io",
    "mainnet.optimism.io",
    "binance.llamarpc.com",
    "api.etherscan.io",
    "api.blockchair.com",
    "api.koios.rest",
    "localhost",
    "127.0.0.1",
}


def register_allowed_host(host_or_url: Optional[str]) -> None:
    """Register custom RPC hosts from environment variables into SSRF allowlist."""
    if not host_or_url:
        return
    try:
        parsed = urllib.parse.urlparse(host_or_url)
        host = parsed.hostname or host_or_url.split(":")[0]
        if host:
            ALLOWED_HOSTS.add(host.lower())
    except Exception:
        pass


def sanitize_source_url(raw_url: str) -> str:
    """Strips API keys, tokens, and credentials from provider URLs before returning to client."""
    try:
        parsed = urllib.parse.urlsplit(raw_url)
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        sanitized_pairs = []
        for k, v in query_pairs:
            lower_k = k.lower()
            if any(secret in lower_k for secret in ("key", "token", "secret", "auth", "apikey")):
                continue
            sanitized_pairs.append((k, v))
        new_query = urllib.parse.urlencode(sanitized_pairs)
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, ""))
    except Exception:
        return raw_url


def is_ssrf_safe(url: str) -> bool:
    """Enforces that URL host is strictly contained within ALLOWED_HOSTS."""
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return hostname in ALLOWED_HOSTS
    except Exception:
        return False


def get_cached_response(key: str) -> Optional[Any]:
    now = time.time()
    if key in _PROVIDER_CACHE:
        expiry, val = _PROVIDER_CACHE[key]
        if now < expiry:
            return val
        else:
            del _PROVIDER_CACHE[key]
    return None


def set_cached_response(key: str, val: Any, ttl: float = _CACHE_TTL_SECONDS) -> None:
    _PROVIDER_CACHE[key] = (time.time() + ttl, val)


class ChainAdapter(ABC):
    """Abstract interface for multi-chain on-chain data providers."""

    chain: str
    source_name: str
    network: str = "mainnet"

    def __init__(self, concurrency_limit: int = 5):
        self._semaphore = asyncio.Semaphore(concurrency_limit)

    def is_demo_mode(self) -> bool:
        return os.environ.get("DEMO_MODE", "").lower() in ("true", "1", "yes")

    def _format_result(
        self,
        *,
        status: str,
        summary: Optional[Dict[str, Any]] = None,
        transactions: Optional[List[Dict[str, Any]]] = None,
        source_url: str = "",
        error: Optional[str] = None,
        labels: Optional[List[Dict[str, Any]]] = None,
        network: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Constructs canonical result dictionary matching the API contract."""
        res: Dict[str, Any] = {
            "chain": self.chain,
            "network": network or self.network,
            "status": status,  # ok | not_found | unavailable | not_applicable | unsupported_lookup
            "summary": summary or {},
            "transactions": transactions or [],
            "labels": labels or [],
            "source": self.source_name,
            "source_url": sanitize_source_url(source_url),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }
        if self.is_demo_mode():
            res["demo"] = True
        return res

    async def _safe_request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
        max_retries: int = 2,
    ) -> Tuple[Optional[httpx.Response], Optional[str]]:
        """Executes an HTTP request with SSRF allowlisting, 10s timeout, retries, and caching."""
        if not is_ssrf_safe(url):
            return None, f"SSRF blocked: host for '{url}' is not in fixed allowlist"

        # Cache key based on method, URL, and payload
        cache_key = f"{method}:{url}:{params}:{json_data}"
        cached = get_cached_response(cache_key)
        if cached is not None:
            return cached, None

        async with self._semaphore:
            backoff = 0.5
            last_err: Optional[str] = None

            for attempt in range(max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        resp = await client.request(
                            method,
                            url,
                            headers=headers,
                            json=json_data,
                            params=params,
                        )

                        # Retry on 429 (Rate Limit) or 5xx (Server Error)
                        if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2.0
                            continue

                        # Cache 200/404 responses
                        if resp.status_code in (200, 404):
                            set_cached_response(cache_key, resp)
                        return resp, None

                except httpx.TimeoutException:
                    return None, f"Request to {self.source_name} timed out after {timeout}s"
                except httpx.RequestError as exc:
                    return None, f"Network error contacting {self.source_name}: {exc}"
                except Exception as exc:
                    return None, f"Unexpected error contacting {self.source_name}: {exc}"

            return None, last_err or "Provider request failed after retries"

    @abstractmethod
    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        """Fetch balance, transaction count, and recent transactions for an address."""
        pass

    @abstractmethod
    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        """Probe transaction hash and return details if present on this chain."""
        pass
