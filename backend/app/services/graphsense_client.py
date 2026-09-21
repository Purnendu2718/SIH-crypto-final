"""Live GraphSense Hosted API Client Adapter.
Interacts with the public/hosted GraphSense API (https://api.ikna.io)
for real-time cluster and entity attribution when an address is not found in the local dataset.
Applies timeout, TTL caching, and best-effort fallback discipline.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8E.
"""

import logging
from typing import Optional, Dict, Any, List
import httpx

from app.config import settings
from app.services.adapters.cache import adapter_cache

logger = logging.getLogger("sentinel.graphsense_client")


class GraphSenseClient:
    """Live entity and cluster lookup client for GraphSense REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 5.0,
    ):
        self.base_url = (base_url or settings.GRAPHSENSE_API_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.GRAPHSENSE_API_KEY
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "CryptoTrace-Sentinel/0.1.0",
        }
        if self.api_key:
            headers["Authorization"] = self.api_key
        return headers

    def lookup_address_entity(self, address: str, chain: str) -> Optional[Dict[str, Any]]:
        """Query GET /{currency}/addresses/{address}/entity.
        Returns parsed entity dict or None on miss/auth-required/rate-limit/network failure.
        """
        clean_addr = address.strip()
        currency = chain.strip().lower()
        if currency == "eth":
            currency = "eth"
        elif currency == "btc":
            currency = "btc"
        elif currency == "tron":
            currency = "trx"

        cache_key = f"gs:entity:{currency}:{clean_addr.lower()}"
        cached = adapter_cache.get(cache_key)
        if cached is not None:
            data, is_stale = cached
            if not is_stale and data is not None:
                return data

        url = f"{self.base_url}/{currency}/addresses/{clean_addr}/entity"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    # Extract best tag or actor label
                    best_tag = data.get("best_address_tag") or {}
                    actors = data.get("actors") or []

                    entity_label = (
                        best_tag.get("label")
                        or (actors[0].get("label") if actors else None)
                        or (f"GraphSense Cluster #{data.get('cluster')}" if data.get("cluster") else None)
                    )
                    actor_id = best_tag.get("actor") or (actors[0].get("id") if actors else None)
                    category = best_tag.get("category")
                    categories = [category] if category else []

                    if entity_label:
                        result = {
                            "entity_name": entity_label,
                            "actor_id": actor_id,
                            "category": category,
                            "categories": categories,
                            "cluster_id": data.get("cluster"),
                            "source": "LIVE_GRAPHSENSE_API",
                            "raw": data,
                        }
                        adapter_cache.set(cache_key, result, has_low_confirmation=False)
                        return result

                elif resp.status_code == 404:
                    # Address is unclustered / not found in GraphSense
                    logger.debug(f"[GraphSense Client] Address {clean_addr} not clustered (HTTP 404).")
                elif resp.status_code == 401:
                    logger.warning(f"[GraphSense Client] API at {self.base_url} returned 401 Authorization Required. Treated as supplementary best-effort fallback.")
                elif resp.status_code == 429:
                    logger.warning(f"[GraphSense Client] Rate limit exceeded on {self.base_url} (HTTP 429).")
                else:
                    logger.warning(f"[GraphSense Client] Unexpected response {resp.status_code} for {clean_addr}.")
        except httpx.TimeoutException:
            logger.warning(f"[GraphSense Client] Request timed out after {self.timeout}s for {clean_addr}.")
        except Exception as ex:
            logger.warning(f"[GraphSense Client] Failed connecting to {url}: {ex}")

        # Best-effort fallback: record negative cache briefly to prevent hammering
        adapter_cache.set(cache_key, None, has_low_confirmation=True)
        return None

    def lookup_address_neighbors(self, address: str, chain: str) -> Optional[List[Dict[str, Any]]]:
        """Query GET /{currency}/addresses/{address}/neighbors for cluster topological links."""
        clean_addr = address.strip()
        currency = chain.strip().lower()
        if currency == "tron":
            currency = "trx"

        cache_key = f"gs:neighbors:{currency}:{clean_addr.lower()}"
        cached = adapter_cache.get(cache_key)
        if cached is not None:
            data, is_stale = cached
            if not is_stale and data is not None:
                return data

        url = f"{self.base_url}/{currency}/addresses/{clean_addr}/neighbors"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers=self._get_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    neighbors = data.get("neighbors", [])
                    adapter_cache.set(cache_key, neighbors, has_low_confirmation=False)
                    return neighbors
        except Exception as ex:
            logger.warning(f"[GraphSense Client] Neighbors query failed for {clean_addr}: {ex}")

        return None
