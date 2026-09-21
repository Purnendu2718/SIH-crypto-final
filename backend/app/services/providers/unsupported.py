"""Unsupported Lookup Adapter for chains where validation is implemented but live lookup is unconfigured.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.providers.base import ChainAdapter


class UnsupportedLookupAdapter(ChainAdapter):
    def __init__(self, chain_name: str = "unknown", source_name: str = "CryptoTrace Sentinel"):
        super().__init__()
        self.chain = chain_name
        self.source_name = source_name

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        msg = f"Address format validated. Live on-chain lookup for {self.chain} is currently unsupported in this deployment."
        return self._format_result(
            status="unsupported_lookup",
            summary={"note": msg},
            error=msg,
            source_url="https://github.com",
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        msg = f"Transaction hash format validated. Live on-chain lookup for {self.chain} is currently unsupported in this deployment."
        return self._format_result(
            status="unsupported_lookup",
            summary={"note": msg},
            error=msg,
            source_url="https://github.com",
            network=network,
        )
