"""Bitcoin Adapter using mempool.space Esplora API with blockstream.info fallback.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter
from app.services.providers.entities import get_known_entity_labels


class BitcoinAdapter(ChainAdapter):
    chain = "bitcoin"
    source_name = "mempool.space"

    def _get_base_urls(self, network: str) -> List[str]:
        if network == "testnet":
            return [
                "https://mempool.space/testnet/api",
                "https://blockstream.info/testnet/api",
            ]
        return [
            "https://mempool.space/api",
            "https://blockstream.info/api",
        ]

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_addr = urllib.parse.quote(address.strip(), safe="")
        labels = get_known_entity_labels(address.strip(), self.chain)
        base_urls = self._get_base_urls(network)

        last_error = None
        for base_url in base_urls:
            addr_url = f"{base_url}/address/{clean_addr}"
            txs_url = f"{base_url}/address/{clean_addr}/txs"

            resp, err = await self._safe_request("GET", addr_url)
            if err or resp is None:
                last_error = err or "Connection failed"
                continue

            if resp.status_code == 404:
                return self._format_result(
                    status="not_found",
                    summary={"balance": 0.0, "balance_formatted": "0.00000000 BTC", "tx_count": 0},
                    source_url=addr_url,
                    labels=labels,
                    network=network,
                )

            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code} from {base_url}"
                continue

            try:
                data = resp.json()
            except Exception as e:
                last_error = f"Invalid JSON response: {e}"
                continue

            chain_stats = data.get("chain_stats", {})
            mempool_stats = data.get("mempool_stats", {})

            funded = chain_stats.get("funded_txo_sum", 0) + mempool_stats.get("funded_txo_sum", 0)
            spent = chain_stats.get("spent_txo_sum", 0) + mempool_stats.get("spent_txo_sum", 0)
            balance_sats = funded - spent
            balance_btc = balance_sats / 1e8
            tx_count = chain_stats.get("tx_count", 0) + mempool_stats.get("tx_count", 0)

            # Fetch recent transactions
            tx_records: List[Dict[str, Any]] = []
            tx_resp, _ = await self._safe_request("GET", txs_url)
            if tx_resp is not None and tx_resp.status_code == 200:
                try:
                    raw_txs = tx_resp.json()
                    if isinstance(raw_txs, list):
                        for tx in raw_txs[:20]:
                            txid = tx.get("txid", "")
                            status_obj = tx.get("status", {})
                            b_time = status_obj.get("block_time")
                            time_iso = (
                                datetime.fromtimestamp(b_time, tz=timezone.utc).isoformat()
                                if b_time
                                else None
                            )

                            # Calculate net amount for this address
                            in_sum = sum(
                                vin.get("prevout", {}).get("value", 0)
                                for vin in tx.get("vin", [])
                                if vin.get("prevout", {}).get("scriptpubkey_address") == address
                            )
                            out_sum = sum(
                                vout.get("value", 0)
                                for vout in tx.get("vout", [])
                                if vout.get("scriptpubkey_address") == address
                            )
                            net_sats = out_sum - in_sum
                            explorer_net = "/testnet" if network == "testnet" else ""

                            tx_records.append({
                                "hash": txid,
                                "time": time_iso,
                                "amount": round(net_sats / 1e8, 8),
                                "fee": round(tx.get("fee", 0) / 1e8, 8),
                                "confirmed": status_obj.get("confirmed", False),
                                "block_height": status_obj.get("block_height"),
                                "explorer_url": f"https://mempool.space{explorer_net}/tx/{txid}",
                            })
                except Exception:
                    pass

            summary = {
                "balance": balance_btc,
                "balance_satoshis": balance_sats,
                "balance_formatted": f"{balance_btc:.8f} BTC",
                "tx_count": tx_count,
            }

            return self._format_result(
                status="ok",
                summary=summary,
                transactions=tx_records,
                source_url=addr_url,
                labels=labels,
                network=network,
            )

        return self._format_result(
            status="unavailable",
            error=last_error or "All Bitcoin Esplora endpoints unreachable",
            source_url=f"{base_urls[0]}/address/{clean_addr}",
            labels=labels,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_tx = urllib.parse.quote(tx_hash.strip(), safe="")
        base_urls = self._get_base_urls(network)

        for base_url in base_urls:
            tx_url = f"{base_url}/tx/{clean_tx}"
            resp, err = await self._safe_request("GET", tx_url)
            if err or resp is None:
                continue

            if resp.status_code == 404:
                return self._format_result(
                    status="not_found",
                    source_url=tx_url,
                    network=network,
                )

            if resp.status_code == 200:
                try:
                    tx = resp.json()
                    status_obj = tx.get("status", {})
                    b_time = status_obj.get("block_time")
                    time_iso = (
                        datetime.fromtimestamp(b_time, tz=timezone.utc).isoformat()
                        if b_time
                        else None
                    )
                    vouts = [
                        {
                            "address": vo.get("scriptpubkey_address"),
                            "value": round(vo.get("value", 0) / 1e8, 8),
                        }
                        for vo in tx.get("vout", [])
                        if vo.get("scriptpubkey_address")
                    ]
                    explorer_net = "/testnet" if network == "testnet" else ""

                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": tx.get("txid"),
                            "fee": round(tx.get("fee", 0) / 1e8, 8),
                            "confirmed": status_obj.get("confirmed", False),
                            "block_height": status_obj.get("block_height"),
                            "block_time": time_iso,
                            "outputs": vouts,
                        },
                        source_url=tx_url,
                        network=network,
                    )
                except Exception:
                    pass

        return self._format_result(
            status="unavailable",
            error="Bitcoin Esplora transaction lookup unreachable",
            source_url=f"{base_urls[0]}/tx/{clean_tx}",
            network=network,
        )
