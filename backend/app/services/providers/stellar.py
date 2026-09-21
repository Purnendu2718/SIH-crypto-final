"""Stellar Horizon REST Adapter.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter
from app.services.providers.entities import get_known_entity_labels


class StellarAdapter(ChainAdapter):
    chain = "stellar"
    source_name = "Stellar Horizon"

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_addr = urllib.parse.quote(address.strip(), safe="")
        labels = get_known_entity_labels(address.strip(), self.chain)

        base_url = "https://horizon.stellar.org"
        acct_url = f"{base_url}/accounts/{clean_addr}"
        txs_url = f"{base_url}/accounts/{clean_addr}/transactions?order=desc&limit=20"

        resp, err = await self._safe_request("GET", acct_url)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Stellar Horizon",
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": "0.0000000 XLM", "tx_count": 0},
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        if resp.status_code != 200:
            return self._format_result(
                status="unavailable",
                error=f"Horizon returned HTTP {resp.status_code}",
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        try:
            data = resp.json()
        except Exception as e:
            return self._format_result(
                status="unavailable",
                error=f"Invalid JSON from Horizon: {e}",
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        balances = data.get("balances", [])
        native_bal = 0.0
        for b in balances:
            if b.get("asset_type") == "native":
                try:
                    native_bal = float(b.get("balance", 0.0))
                except (ValueError, TypeError):
                    pass
                break

        # Recent transactions
        tx_records: List[Dict[str, Any]] = []
        tx_resp, _ = await self._safe_request("GET", txs_url)
        if tx_resp is not None and tx_resp.status_code == 200:
            try:
                records = tx_resp.json().get("_embedded", {}).get("records", [])
                for r in records[:20]:
                    tx_hash = r.get("hash") or r.get("id")
                    tx_records.append({
                        "hash": tx_hash,
                        "time": r.get("created_at"),
                        "successful": r.get("successful", True),
                        "fee": float(r.get("fee_charged", 0)) / 1e7,
                        "explorer_url": f"https://stellar.expert/explorer/public/tx/{tx_hash}",
                    })
            except Exception:
                pass

        summary = {
            "balance": native_bal,
            "balance_formatted": f"{native_bal:,.7f} XLM",
            "sequence": data.get("sequence"),
            "subentry_count": data.get("subentry_count"),
            "tx_count": len(tx_records),
        }

        return self._format_result(
            status="ok",
            summary=summary,
            transactions=tx_records,
            source_url=acct_url,
            labels=labels,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_tx = urllib.parse.quote(tx_hash.strip(), safe="")
        url = f"https://horizon.stellar.org/transactions/{clean_tx}"

        resp, err = await self._safe_request("GET", url)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Stellar Horizon",
                source_url=url,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(status="not_found", source_url=url, network=network)

        if resp.status_code == 200:
            try:
                r = resp.json()
                return self._format_result(
                    status="ok",
                    summary={
                        "tx_hash": r.get("hash"),
                        "created_at": r.get("created_at"),
                        "successful": r.get("successful"),
                        "fee_charged": r.get("fee_charged"),
                    },
                    source_url=url,
                    network=network,
                )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=url, network=network)
