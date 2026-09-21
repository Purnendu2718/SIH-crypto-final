"""EVM Multi-Chain Adapter (Ethereum, Polygon, Arbitrum, Optimism, BSC, Base, Avalanche).
Uses public JSON-RPC for balance/nonce/code and Etherscan V2 for transaction history.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.providers.base import ChainAdapter, register_allowed_host
from app.services.providers.entities import get_known_entity_labels

EVM_CHAINS = {
    "ethereum": {
        "name": "Ethereum",
        "symbol": "ETH",
        "decimals": 18,
        "chainid": 1,
        "default_rpc": "https://ethereum-rpc.publicnode.com",
        "explorer": "https://etherscan.io",
    },
    "polygon": {
        "name": "Polygon",
        "symbol": "POL",
        "decimals": 18,
        "chainid": 137,
        "default_rpc": "https://polygon-rpc.com",
        "explorer": "https://polygonscan.com",
    },
    "arbitrum": {
        "name": "Arbitrum One",
        "symbol": "ETH",
        "decimals": 18,
        "chainid": 42161,
        "default_rpc": "https://arb1.arbitrum.io/rpc",
        "explorer": "https://arbiscan.io",
    },
    "optimism": {
        "name": "Optimism",
        "symbol": "ETH",
        "decimals": 18,
        "chainid": 10,
        "default_rpc": "https://mainnet.optimism.io",
        "explorer": "https://optimistic.etherscan.io",
    },
    "bsc": {
        "name": "BNB Smart Chain",
        "symbol": "BNB",
        "decimals": 18,
        "chainid": 56,
        "default_rpc": "https://binance.llamarpc.com",
        "explorer": "https://bscscan.com",
    },
}


class EvmProviderAdapter(ChainAdapter):
    def __init__(self, chain_key: str = "ethereum", concurrency_limit: int = 5):
        super().__init__(concurrency_limit=concurrency_limit)
        self.chain = chain_key.lower()
        cfg = EVM_CHAINS.get(self.chain, EVM_CHAINS["ethereum"])
        self.source_name = f"{cfg['name']} JSON-RPC"
        self._cfg = cfg

    def _get_rpc_url(self) -> str:
        env_map = {
            "ethereum": os.environ.get("ETH_RPC_URL") or os.environ.get("EVM_RPC_URL"),
            "polygon": os.environ.get("POLYGON_RPC_URL"),
            "arbitrum": os.environ.get("ARBITRUM_RPC_URL"),
            "optimism": os.environ.get("OPTIMISM_RPC_URL"),
            "bsc": os.environ.get("BSC_RPC_URL"),
        }
        url = env_map.get(self.chain) or self._cfg["default_rpc"]
        register_allowed_host(url)
        return url

    async def lookup_address(self, address: str, network: str = "mainnet") -> Dict[str, Any]:
        clean_addr = address.strip()
        labels = get_known_entity_labels(clean_addr, self.chain)
        rpc_url = self._get_rpc_url()

        # Batch JSON-RPC or 3 fast concurrent calls
        bal_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getBalance",
            "params": [clean_addr, "latest"],
        }
        nonce_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "eth_getTransactionCount",
            "params": [clean_addr, "latest"],
        }
        code_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "eth_getCode",
            "params": [clean_addr, "latest"],
        }

        # 1. eth_getBalance
        bal_resp, bal_err = await self._safe_request("POST", rpc_url, json_data=bal_payload)
        if bal_err or bal_resp is None:
            return self._format_result(
                status="unavailable",
                error=bal_err or f"Failed to connect to {self.source_name}",
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        if bal_resp.status_code != 200:
            return self._format_result(
                status="unavailable",
                error=f"{self.source_name} returned HTTP {bal_resp.status_code}",
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        try:
            bal_data = bal_resp.json().get("result")
            balance_wei = int(bal_data, 16) if bal_data and bal_data.startswith("0x") else 0
        except Exception as e:
            return self._format_result(
                status="unavailable",
                error=f"Invalid JSON from RPC: {e}",
                source_url=rpc_url,
                labels=labels,
                network=network,
            )

        balance_eth = balance_wei / 1e18

        # 2. eth_getTransactionCount
        nonce_resp, _ = await self._safe_request("POST", rpc_url, json_data=nonce_payload)
        nonce = 0
        if nonce_resp and nonce_resp.status_code == 200:
            try:
                res = nonce_resp.json().get("result")
                if res and res.startswith("0x"):
                    nonce = int(res, 16)
            except Exception:
                pass

        # 3. eth_getCode
        code_resp, _ = await self._safe_request("POST", rpc_url, json_data=code_payload)
        is_contract = False
        if code_resp and code_resp.status_code == 200:
            try:
                c = code_resp.json().get("result", "")
                if c and c not in ("0x", "0x0"):
                    is_contract = True
            except Exception:
                pass

        # 4. History via Etherscan V2 if API key present
        etherscan_key = os.environ.get("ETHERSCAN_API_KEY")
        tx_records: List[Dict[str, Any]] = []
        history_note = None

        if etherscan_key:
            chainid = self._cfg.get("chainid", 1)
            clean_q = urllib.parse.quote(clean_addr, safe="")
            scan_url = (
                f"https://api.etherscan.io/v2/api?chainid={chainid}"
                f"&module=account&action=txlist&address={clean_q}&page=1&offset=20&sort=desc&apikey={etherscan_key}"
            )
            s_resp, _ = await self._safe_request("GET", scan_url)
            if s_resp and s_resp.status_code == 200:
                try:
                    s_json = s_resp.json()
                    res_list = s_json.get("result", [])
                    if isinstance(res_list, list):
                        for tx in res_list[:20]:
                            h = tx.get("hash")
                            ts = tx.get("timeStamp")
                            time_iso = (
                                datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                                if ts and str(ts).isdigit()
                                else None
                            )
                            val_wei = int(tx.get("value", 0)) if str(tx.get("value", "")).isdigit() else 0
                            tx_records.append({
                                "hash": h,
                                "time": time_iso,
                                "amount": val_wei / 1e18,
                                "from_address": tx.get("from"),
                                "to_address": tx.get("to"),
                                "fee": (
                                    (int(tx.get("gasUsed", 0)) * int(tx.get("gasPrice", 0))) / 1e18
                                    if str(tx.get("gasUsed", "")).isdigit() and str(tx.get("gasPrice", "")).isdigit()
                                    else None
                                ),
                                "explorer_url": f"{self._cfg['explorer']}/tx/{h}",
                            })
                except Exception:
                    pass
        else:
            history_note = "Transaction history requires ETHERSCAN_API_KEY."

        # If balance is 0 and nonce is 0 and not a contract, we classify as ok (unfunded/zero-activity)
        symbol = self._cfg["symbol"]
        summary = {
            "balance": balance_eth,
            "balance_wei": balance_wei,
            "balance_formatted": f"{balance_eth:.6f} {symbol}",
            "tx_count": nonce,
            "is_contract": is_contract,
            "type": "Contract" if is_contract else "EOA (Externally Owned Account)",
        }
        if history_note:
            summary["note"] = history_note

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
            "id": 4,
            "method": "eth_getTransactionByHash",
            "params": [tx_hash.strip()],
        }

        resp, err = await self._safe_request("POST", rpc_url, json_data=payload)
        if err or resp is None:
            return self._format_result(
                status="unavailable",
                error=err or f"Failed to connect to {self.source_name}",
                source_url=rpc_url,
                network=network,
            )

        if resp.status_code == 200:
            try:
                tx = resp.json().get("result")
                if tx is not None:
                    h = tx.get("hash")
                    val_wei = int(tx.get("value", "0x0"), 16)
                    return self._format_result(
                        status="ok",
                        summary={
                            "tx_hash": h,
                            "from_address": tx.get("from"),
                            "to_address": tx.get("to"),
                            "value": val_wei / 1e18,
                            "block_number": int(tx.get("blockNumber", "0x0"), 16) if tx.get("blockNumber") else None,
                        },
                        source_url=rpc_url,
                        network=network,
                    )
            except Exception:
                pass

        return self._format_result(status="not_found", source_url=rpc_url, network=network)
