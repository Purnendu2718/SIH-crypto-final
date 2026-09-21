"""Monero Privacy Adapter.
Monero uses ring signatures, stealth addresses, and RingCT; on-chain balance
and history cannot be cryptographically derived from a public address alone.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.providers.base import ChainAdapter


class MoneroAdapter(ChainAdapter):
    chain = "monero"
    source_name = "Monero Cryptographic Design"

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        note = (
            "Privacy chain: balance and history cannot be derived from a public address alone "
            "(stealth addresses and RingCT mask amounts and destinations)."
        )
        return self._format_result(
            status="not_applicable",
            summary={"note": note, "is_privacy_chain": True},
            source_url="https://www.getmonero.org/resources/moneropedia/stealthaddress.html",
            error=note,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        note = "Privacy chain: transaction inputs/outputs are cryptographically obfuscated."
        return self._format_result(
            status="not_applicable",
            summary={"note": note, "is_privacy_chain": True},
            source_url="https://www.getmonero.org/resources/moneropedia/ringsignatures.html",
            error=note,
            network=network,
        )
