"""Solana JSON-RPC Adapter.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter, register_allowed_host
from app.services.providers.entities import get_known_entity_labels


class SolanaAdapter(ChainAdapter):
    chain = "solana"
    source_name = "Solana JSON-RPC"

    def _get_rpc_url(self) -> str:
        url = os.environ.get("SOLANA_RPC_URL") or "https://api.mainnet-beta.solana.com"
        register_allowed_host(url)
        return url

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        labels = get_known_entity_labels(address.strip(), self.chain)
        rpc_url = self._get_rpc_url()

        # 1. getAccountInfo to check existence
        acct_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [address.strip(), {"encoding": "base64"}],
        }
        resp, err = await self._safe_request("POST", rpc_url, json_data=acct_payload)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Solana RPC",
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        if resp.status_code != 200:
            return self._format_result(
                status="unavailable",
                error=f"Solana RPC returned HTTP {resp.status_code}",
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        try:
            data = resp.json()
        except Exception as e:
            return self._format_result(
                status="unavailable",
                error=f"Invalid JSON from Solana RPC: {e}",
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        result_val = data.get("result", {}).get("value")
        if result_val is None:
            return self._format_result(
                status="not_found",
                summary={"balance": 0.0, "balance_formatted": "0.000000000 SOL", "tx_count": 0},
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        lamports = result_val.get("lamports", 0)
        balance_sol = lamports / 1e9

        # 2. getSignaturesForAddress for recent transactions
        sig_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "getSignaturesForAddress",
            "params": [address.strip(), {"limit": 20}],
        }
        tx_records: List[Dict[str, Any]] = []
        sig_resp, _ = await self._safe_request("POST", rpc_url, json_data=sig_payload)
        if sig_resp is not None and sig_resp.status_code == 200:
            try:
                sig_data = sig_resp.json()
                sigs = sig_data.get("result", [])
                if isinstance(sigs, list):
                    for s in sigs:
                        sig = s.get("signature")
                        b_time = s.get("blockTime")
                        time_iso = (
                            datetime.fromtimestamp(b_time, tz=timezone.utc).isoformat()
                            if b_time
                            else None
                        )
                        tx_records.append({
                            "hash": sig,
                            "time": time_iso,
                            "confirmation_status": s.get("confirmationStatus"),
                            "explorer_url": f"https://solscan.io/tx/{sig}",
                        })
            except Exception:
                pass

        summary = {
            "balance": balance_sol,
            "balance_lamports": lamports,
            "balance_formatted": f"{balance_sol:.9f} SOL",
            "tx_count": len(tx_records),
            "owner": result_val.get("owner"),
            "executable": result_val.get("executable", False),
        }

        return self._format_result(
            status="ok",
            summary=summary,
            transactions=tx_records,
            source_url=rpc_url,
            labels=labels,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        rpc_url = self._get_rpc_url()
        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "getTransaction",
            "params": [
                tx_hash.strip(),
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0},
            ],
        }

        resp, err = await self._safe_request("POST", rpc_url, json_data=payload)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or "Failed to connect to Solana RPC",
                source_url=rpc_url,
                network=network,
            )

        if resp.status_code == 200:
            try:
                res = resp.json().get("result")
                if res is not None:
                    b_time = res.get("blockTime")
                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": tx_hash,
                            "slot": res.get("slot"),
                            "block_time": (
                                datetime.fromtimestamp(b_time, tz=timezone.utc).isoformat()
                                if b_time
                                else None
                            ),
                        },
                        source_url=rpc_url,
                        network=network,
                    )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=rpc_url, network=network)
