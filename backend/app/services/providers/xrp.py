"""XRP Ledger (XRPL) JSON-RPC Adapter.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter
from app.services.providers.entities import get_known_entity_labels

RIPPLE_EPOCH = 946684800  # Jan 1, 2000 00:00:00 UTC


class XrpAdapter(ChainAdapter):
    chain = "xrp_ledger"
    source_name = "XRPL JSON-RPC"

    def _get_rpc_urls(self) -> List[str]:
        return [
            "https://xrplcluster.com",
            "https://s1.ripple.com:51234",
        ]

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        labels = get_known_entity_labels(address.strip(), self.chain)
        clean_addr = address.strip()

        last_error = None
        for rpc_url in self._get_rpc_urls():
            # 1. account_info
            payload = {
                "method": "account_info",
                "params": [{"account": clean_addr, "ledger_index": "validated"}],
            }
            resp, err = await self._safe_request("POST", rpc_url, json_data=payload)
            if err or resp is None:
                last_error = err or "Connection failed"
                continue

            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code} from {rpc_url}"
                continue

            try:
                data = resp.json().get("result", {})
            except Exception as e:
                last_error = f"Invalid JSON: {e}"
                continue

            error_code = data.get("error")
            if error_code == "actNotFound":
                return self._format_result(
                    status="not_found",
                    summary={"balance": 0.0, "balance_formatted": "0.000000 XRP", "tx_count": 0},
                    source_url=rpc_url,
                    labels=labels,
                    network=network,
                )

            account_data = data.get("account_data")
            if not account_data:
                last_error = data.get("error_message") or error_code or "Unknown error"
                continue

            drops = int(account_data.get("Balance", 0))
            balance_xrp = drops / 1e6

            # 2. account_tx
            tx_payload = {
                "method": "account_tx",
                "params": [{"account": clean_addr, "limit": 20}],
            }
            tx_records: List[Dict[str, Any]] = []
            tx_resp, _ = await self._safe_request("POST", rpc_url, json_data=tx_payload)
            if tx_resp is not None and tx_resp.status_code == 200:
                try:
                    tx_data = tx_resp.json().get("result", {})
                    transactions = tx_data.get("transactions", [])
                    for t in transactions[:20]:
                        tx = t.get("tx") or t.get("tx_json") or {}
                        h = tx.get("hash")
                        d = tx.get("date")
                        time_iso = None
                        if d is not None:
                            time_iso = datetime.fromtimestamp(RIPPLE_EPOCH + d, tz=timezone.utc).isoformat()

                        amount_drops = tx.get("Amount")
                        amount_xrp = None
                        if isinstance(amount_drops, (int, str)) and str(amount_drops).isdigit():
                            amount_xrp = int(amount_drops) / 1e6

                        tx_records.append({
                            "hash": h,
                            "time": time_iso,
                            "amount": amount_xrp,
                            "fee": int(tx.get("Fee", 0)) / 1e6 if str(tx.get("Fee", "")).isdigit() else None,
                            "explorer_url": f"https://xrpscan.com/tx/{h}",
                        })
                except Exception:
                    pass

            summary = {
                "balance": balance_xrp,
                "balance_drops": drops,
                "balance_formatted": f"{balance_xrp:,.6f} XRP",
                "sequence": account_data.get("Sequence"),
                "tx_count": len(tx_records),
            }

            return self._format_result(
                status="ok",
                summary=summary,
                transactions=tx_records,
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        return self._format_result(
            status="unavailable",
            error=last_error or "XRPL nodes unreachable",
            source_url=self._get_rpc_urls()[0],
            labels=labels,
            network=network,
        )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> Dict[str, Any]:
        payload = {"method": "tx", "params": [{"transaction": tx_hash.strip(), "binary": False}]}
        for rpc_url in self._get_rpc_urls():
            resp, err = await self._safe_request("POST", rpc_url, json_data=payload)
            if err or resp is None or resp.status_code != 200:
                continue

            try:
                res = resp.json().get("result", {})
                if res.get("error") == "txnNotFound":
                    return self._format_result(status="not_found", source_url=rpc_url, network=network)

                if res.get("hash"):
                    d = res.get("date")
                    time_iso = None
                    if d is not None:
                        time_iso = datetime.fromtimestamp(RIPPLE_EPOCH + d, tz=timezone.utc).isoformat()

                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": res.get("hash"),
                            "ledger_index": res.get("ledger_index"),
                            "date": time_iso,
                        },
                        source_url=rpc_url,
                        network=network,
                    )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=self._get_rpc_urls()[0], network=network)
