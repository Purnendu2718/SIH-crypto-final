"""Cardano Adapter using Koios public REST API.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter
from app.services.providers.entities import get_known_entity_labels


class CardanoAdapter(ChainAdapter):
    chain = "cardano"
    source_name = "Koios"

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_addr = address.strip()
        labels = get_known_entity_labels(clean_addr, self.chain)

        base_url = "https://api.koios.rest/api/v1"
        info_url = f"{base_url}/address_info"
        txs_url = f"{base_url}/address_txs"

        resp, err = await self._safe_request("POST", info_url, json_data={"_addresses": [clean_addr]})
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Koios",
                source_url=info_url,
                labels=labels,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": "0.000000 ADA", "tx_count": 0},
                source_url=info_url,
                labels=labels,
                network=network,
            )

        if resp.status_code != 200:
            return self._format_result(
                status="unavailable",
                error=f"Koios returned HTTP {resp.status_code}",
                source_url=info_url,
                labels=labels,
                network=network,
            )

        try:
            items = resp.json()
        except Exception as e:
            return self._format_result(
                status="unavailable",
                error=f"Invalid JSON from Koios: {e}",
                source_url=info_url,
                labels=labels,
                network=network,
            )

        if not items or not isinstance(items, list):
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": "0.000000 ADA", "tx_count": 0},
                source_url=info_url,
                labels=labels,
                network=network,
            )

        info = items[0]
        balance_lovelace = int(info.get("balance", 0)) if str(info.get("balance", "")).isdigit() else 0
        balance_ada = balance_lovelace / 1e6
        tx_count = info.get("tx_count", 0)

        # Recent transactions
        tx_records: List[Dict[str, Any]] = []
        tx_resp, _ = await self._safe_request("POST", txs_url, json_data={"_addresses": [clean_addr]})
        if tx_resp is not None and tx_resp.status_code == 200:
            try:
                tx_list = tx_resp.json()
                if isinstance(tx_list, list):
                    for t in tx_list[:20]:
                        th = t.get("tx_hash")
                        tx_records.append({
                            "hash": th,
                            "block_height": t.get("block_height"),
                            "explorer_url": f"https://cardanoscan.io/transaction/{th}",
                        })
            except Exception:
                pass

        summary = {
            "balance": balance_ada,
            "balance_lovelace": balance_lovelace,
            "balance_formatted": f"{balance_ada:,.6f} ADA",
            "tx_count": tx_count,
        }

        return self._format_result(
            status="ok",
            summary=summary,
            transactions=tx_records,
            source_url=info_url,
            labels=labels,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_tx = tx_hash.strip()
        url = "https://api.koios.rest/api/v1/tx_info"
        resp, err = await self._safe_request("POST", url, json_data={"_tx_hashes": [clean_tx]})
        if err or resp is None:
            return self._format_result(status="unavailable", error=err, source_url=url, network=network)

        if resp.status_code == 200:
            try:
                data = resp.json()
                if data and isinstance(data, list):
                    t = data[0]
                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": t.get("tx_hash"),
                            "block_time": t.get("tx_timestamp"),
                            "fee": int(t.get("fee", 0)) / 1e6 if str(t.get("fee", "")).isdigit() else None,
                        },
                        source_url=url,
                        network=network,
                    )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=url, network=network)
