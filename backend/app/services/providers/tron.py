"""TRON Adapter using TronGrid official REST API.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter
from app.services.providers.entities import get_known_entity_labels


class TronProviderAdapter(ChainAdapter):
    chain = "tron"
    source_name = "TronGrid"

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        api_key = os.environ.get("TRON_PRO_API_KEY") or os.environ.get("TRONGRID_API_KEY")
        if api_key:
            headers["TRON-PRO-API-KEY"] = api_key.strip()
        return headers

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_addr = urllib.parse.quote(address.strip(), safe="")
        labels = get_known_entity_labels(address.strip(), self.chain)

        base_url = "https://api.trongrid.io"
        acct_url = f"{base_url}/v1/accounts/{clean_addr}"
        txs_url = f"{base_url}/v1/accounts/{clean_addr}/transactions?limit=20"

        headers = self._get_headers()
        resp, err = await self._safe_request("GET", acct_url, headers=headers)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to TronGrid",
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": "0.000000 TRX", "tx_count": 0},
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        if resp.status_code != 200:
            return self._format_result(
                status="unavailable",
                error=f"TronGrid responded with HTTP {resp.status_code}",
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        try:
            data = resp.json()
        except Exception as e:
            return self._format_result(
                status="unavailable",
                error=f"Invalid JSON from TronGrid: {e}",
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        accounts = data.get("data", [])
        if not accounts:
            # Tron accounts with 0 activity are often empty list
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": "0.000000 TRX", "tx_count": 0},
                source_url=acct_url,
                labels=labels,
                network=network,
            )

        acct = accounts[0]
        balance_sun = acct.get("balance", 0)
        balance_trx = balance_sun / 1e6
        last_op_ms = acct.get("latest_opration_time")
        last_seen = (
            datetime.fromtimestamp(last_op_ms / 1000, tz=timezone.utc).isoformat()
            if last_op_ms
            else None
        )

        # Recent transactions
        tx_records: List[Dict[str, Any]] = []
        tx_resp, _ = await self._safe_request("GET", txs_url, headers=headers)
        if tx_resp is not None and tx_resp.status_code == 200:
            try:
                tx_json = tx_resp.json()
                for tx in tx_json.get("data", [])[:20]:
                    txid = tx.get("txID", "")
                    ts_ms = tx.get("block_timestamp")
                    time_iso = (
                        datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
                        if ts_ms
                        else None
                    )
                    raw_data = tx.get("raw_data", {})
                    contracts = raw_data.get("contract", [])
                    val_trx = 0.0
                    if contracts:
                        val_sun = (
                            contracts[0]
                            .get("parameter", {})
                            .get("value", {})
                            .get("amount", 0)
                        )
                        val_trx = val_sun / 1e6

                    tx_records.append({
                        "hash": txid,
                        "time": time_iso,
                        "amount": val_trx,
                        "explorer_url": f"https://tronscan.org/#/transaction/{txid}",
                    })
            except Exception:
                pass

        summary = {
            "balance": balance_trx,
            "balance_sun": balance_sun,
            "balance_formatted": f"{balance_trx:,.6f} TRX",
            "tx_count": len(tx_records),
            "last_seen": last_seen,
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
        url = f"https://api.trongrid.io/v1/transactions/{clean_tx}"
        headers = self._get_headers()

        resp, err = await self._safe_request("GET", url, headers=headers)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to TronGrid",
                source_url=url,
                network=network,
            )

        if resp.status_code == 404:
            return self._format_result(status="not_found", source_url=url, network=network)

        if resp.status_code == 200:
            try:
                data = resp.json()
                tx_list = data.get("data", [])
                if tx_list:
                    tx = tx_list[0]
                    ts_ms = tx.get("block_timestamp")
                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": tx.get("txID"),
                            "block_timestamp": (
                                datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()
                                if ts_ms
                                else None
                            ),
                            "ret": tx.get("ret", []),
                        },
                        source_url=url,
                        network=network,
                    )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=url, network=network)
