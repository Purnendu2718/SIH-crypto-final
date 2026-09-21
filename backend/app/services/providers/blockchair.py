"""Blockchair Adapter for UTXO forks: Litecoin, Dogecoin, Dash, Zcash, Bitcoin Cash.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter
from app.services.providers.entities import get_known_entity_labels

BLOCKCHAIR_SLUGS = {
    "litecoin": ("litecoin", "LTC", "https://blockchair.com/litecoin"),
    "dogecoin": ("dogecoin", "DOGE", "https://blockchair.com/dogecoin"),
    "dash": ("dash", "DASH", "https://blockchair.com/dash"),
    "zcash": ("zcash", "ZEC", "https://blockchair.com/zcash"),
    "bitcoin_cash": ("bitcoin-cash", "BCH", "https://blockchair.com/bitcoin-cash"),
}


class BlockchairAdapter(ChainAdapter):
    def __init__(self, chain_key: str = "litecoin", concurrency_limit: int = 5):
        super().__init__(concurrency_limit=concurrency_limit)
        self.chain = chain_key.lower()
        self.source_name = "Blockchair"
        self._slug, self._symbol, self._explorer = BLOCKCHAIR_SLUGS.get(
            self.chain, (self.chain, self.chain.upper(), "https://blockchair.com")
        )

    def _get_api_key(self) -> Optional[str]:
        return os.environ.get("BLOCKCHAIR_API_KEY")

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        raw_addr = address.strip()
        # For BCH cashaddr, strip prefix if needed by blockchair or url encode
        clean_addr = raw_addr.replace("bitcoincash:", "")
        encoded_addr = urllib.parse.quote(clean_addr, safe="")
        labels = get_known_entity_labels(raw_addr, self.chain)

        base_url = f"https://api.blockchair.com/{self._slug}/dashboards/address/{encoded_addr}"
        params = {}
        api_key = self._get_api_key()
        if api_key:
            params["key"] = api_key

        resp, err = await self._safe_request("GET", base_url, params=params)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Blockchair",
                source_url=base_url,
                labels=labels,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": f"0.00000000 {self._symbol}", "tx_count": 0},
                source_url=base_url,
                labels=labels,
                network=network,
            )

        if resp.status_code != 200:
            return self._format_result(
                status="unavailable",
                error=f"Blockchair returned HTTP {resp.status_code}",
                source_url=base_url,
                labels=labels,
                network=network,
            )

        try:
            root = resp.json()
            data_map = root.get("data", {})
            # Key can be clean_addr or lowercased
            addr_data = data_map.get(clean_addr) or (list(data_map.values())[0] if data_map else None)
        except Exception as e:
            return self._format_result(
                status="unavailable",
                error=f"Invalid JSON from Blockchair: {e}",
                source_url=base_url,
                labels=labels,
                network=network,
            )

        if not addr_data:
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": f"0.00000000 {self._symbol}", "tx_count": 0},
                source_url=base_url,
                labels=labels,
                network=network,
            )

        address_info = addr_data.get("address", {})
        bal_sats = address_info.get("balance", 0)
        bal_coin = bal_sats / 1e8
        tx_count = address_info.get("transaction_count", 0)

        # Recent transactions
        tx_hashes = addr_data.get("transactions", [])
        tx_records = [
            {
                "hash": h,
                "explorer_url": f"{self._explorer}/transaction/{h}",
            }
            for h in tx_hashes[:20]
        ]

        summary = {
            "balance": bal_coin,
            "balance_satoshis": bal_sats,
            "balance_formatted": f"{bal_coin:.8f} {self._symbol}",
            "tx_count": tx_count,
            "first_seen": address_info.get("first_seen_receiving"),
            "last_seen": address_info.get("last_seen_receiving"),
        }

        return self._format_result(
            status="ok",
            summary=summary,
            transactions=tx_records,
            source_url=base_url,
            labels=labels,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_tx = urllib.parse.quote(tx_hash.strip(), safe="")
        base_url = f"https://api.blockchair.com/{self._slug}/dashboards/transaction/{clean_tx}"
        params = {}
        api_key = self._get_api_key()
        if api_key:
            params["key"] = api_key

        resp, err = await self._safe_request("GET", base_url, params=params)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Blockchair",
                source_url=base_url,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(status="not_found", source_url=base_url, network=network)

        if resp.status_code == 200:
            try:
                data = resp.json().get("data", {})
                tx_data = data.get(clean_tx) or (list(data.values())[0] if data else None)
                if tx_data:
                    tx_info = tx_data.get("transaction", {})
                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": tx_info.get("hash"),
                            "time": tx_info.get("time"),
                            "fee": tx_info.get("fee", 0) / 1e8,
                            "output_total": tx_info.get("output_total", 0) / 1e8,
                        },
                        source_url=base_url,
                        network=network,
                    )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=base_url, network=network)
