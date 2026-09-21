"""TRON Blockchain Live Adapter.
Supports TronGrid REST API (with or without TRONGRID_API_KEY)
for recent transaction retrieval and historical account queries.
Includes confirmation tracking and cache resilience.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import httpx

from app.config import settings
from app.services.adapters.base import ChainAdapter, NormalizedTransaction
from app.services.adapters.fixture_adapter import FixtureAdapter
from app.services.adapters.cache import adapter_cache

logger = logging.getLogger("sentinel.adapters.tron")


class TronAdapter(ChainAdapter):
    """TRON chain adapter supporting live TronGrid queries (key optional)
    with seamless fallback to FixtureAdapter for offline-first resilience.
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.chain = "TRON"
        self.rpc_url = rpc_url or settings.TRON_RPC_URL or "https://api.trongrid.io"
        self.api_key = api_key or settings.TRONGRID_API_KEY
        self.fixture_adapter = FixtureAdapter()

    def _headers(self) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["TRON-PRO-API-KEY"] = self.api_key
        return headers

    def get_transaction_by_hash(self, tx_hash: str, chain: Optional[str] = None) -> Optional[NormalizedTransaction]:
        """Fetch TRON transaction by ID / hash directly from TronGrid."""
        clean_hash = tx_hash.strip()
        cache_key = f"tron:tx:{clean_hash.lower()}"

        cached = adapter_cache.get(cache_key)
        if cached and not cached[1]:
            return cached[0]

        try:
            url = f"{self.rpc_url.rstrip('/')}/wallet/gettransactionbyid"
            resp = httpx.post(url, json={"value": clean_hash}, headers=self._headers(), timeout=5.0)
            if resp.status_code == 200:
                raw = resp.json()
                if raw and raw.get("txID"):
                    raw_data = raw.get("raw_data", {})
                    contract_list = raw_data.get("contract", [])
                    from_addr = ""
                    to_addr = ""
                    trx_val = 0.0
                    if contract_list:
                        param = contract_list[0].get("parameter", {}).get("value", {})
                        from_addr = param.get("owner_address", "")
                        to_addr = param.get("to_address", "")
                        amount_sun = float(param.get("amount", 0))
                        trx_val = amount_sun / 1e6

                    ret_list = raw.get("ret", [])
                    is_confirmed = bool(ret_list and ret_list[0].get("contractRet") == "SUCCESS")
                    confirmations = 19 if is_confirmed else 0
                    low_conf = not is_confirmed

                    ts_ms = raw_data.get("timestamp", 0)
                    ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)

                    norm_tx = NormalizedTransaction(
                        tx_hash=raw.get("txID", clean_hash),
                        chain="TRON",
                        from_address=from_addr,
                        to_address=to_addr,
                        value=trx_val,
                        value_inr=trx_val * 13.5,
                        timestamp=ts,
                        confirmations=confirmations,
                        is_pending=not is_confirmed,
                        low_confirmation=low_conf,
                        is_stale=False,
                        metadata={"contract_type": contract_list[0].get("type") if contract_list else None},
                    )
                    adapter_cache.set(cache_key, norm_tx, has_low_confirmation=low_conf)
                    return norm_tx
        except Exception as e:
            logger.debug(f"TronGrid gettransactionbyid failed: {e}")
            if cached:
                stale_tx = cached[0]
                stale_tx.is_stale = True
                return stale_tx

        # Check fixture dataset
        for scenario in self.fixture_adapter.dataset.get("scenarios", []):
            for path in scenario.get("paths", []):
                if path.get("tx_hash", "").lower() == clean_hash.lower():
                    return NormalizedTransaction(
                        tx_hash=path.get("tx_hash"),
                        chain=path.get("chain", "TRON"),
                        from_address=path.get("from_addr"),
                        to_address=path.get("to_addr"),
                        value=float(path.get("value", 0)),
                        value_inr=float(path.get("value", 0)) * 13.5,
                        timestamp=datetime.now(timezone.utc),
                        confirmations=19,
                        is_pending=False,
                        low_confirmation=False,
                        metadata={"source": "fixture_fallback"},
                    )
        return None

    def get_transactions(self, address: str, chain: Optional[str] = "TRON") -> List[NormalizedTransaction]:
        target_chain = (chain or self.chain).upper()
        cache_key = f"tron:txs:{address.lower()}"

        cached = adapter_cache.get(cache_key)
        if cached and not cached[1]:
            return cached[0]

        # Attempt live TronGrid query
        try:
            url = f"{self.rpc_url.rstrip('/')}/v1/accounts/{address}/transactions"
            resp = httpx.get(url, headers=self._headers(), params={"limit": 30}, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                raw_txs = data.get("data", [])
                txs: List[NormalizedTransaction] = []
                has_low_conf = False

                for raw in raw_txs:
                    raw_data = raw.get("raw_data", {})
                    contract_list = raw_data.get("contract", [])
                    if not contract_list:
                        continue
                    val_obj = contract_list[0].get("parameter", {}).get("value", {})
                    amount_sun = float(val_obj.get("amount", 0))
                    trx_val = amount_sun / 1e6
                    ts_ms = raw_data.get("timestamp", 0)
                    ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc) if ts_ms else datetime.now(timezone.utc)

                    ret_list = raw.get("ret", [])
                    is_confirmed = bool(ret_list and ret_list[0].get("contractRet") == "SUCCESS")
                    confirmations = 19 if is_confirmed else 0
                    low_conf = not is_confirmed
                    if low_conf:
                        has_low_conf = True

                    txs.append(
                        NormalizedTransaction(
                            tx_hash=raw.get("txID", ""),
                            chain="TRON",
                            from_address=val_obj.get("owner_address", address),
                            to_address=val_obj.get("to_address", ""),
                            value=trx_val,
                            value_inr=trx_val * 13.5,
                            timestamp=ts,
                            block_number=raw.get("blockNumber"),
                            confirmations=confirmations,
                            is_pending=not is_confirmed,
                            low_confirmation=low_conf,
                            is_sweep=False,
                            metadata={"contract_type": contract_list[0].get("type")},
                        )
                    )
                if txs:
                    adapter_cache.set(cache_key, txs, has_low_confirmation=has_low_conf)
                    return txs
        except Exception as e:
            logger.warning(f"TronGrid live query failed ({e}). Checking stale cache or fixture.")
            if cached:
                stale_txs = cached[0]
                for t in stale_txs:
                    t.is_stale = True
                return stale_txs

        # Fallback to fixture adapter
        return self.fixture_adapter.get_transactions(address, target_chain)


# Alias for spec consistency
TronLiveAdapter = TronAdapter
