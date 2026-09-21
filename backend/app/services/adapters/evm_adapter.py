"""EVM-Compatible Blockchain Live Adapter (Ethereum, Polygon, Arbitrum, BSC).
Supports direct JSON-RPC (eth_getTransactionByHash, eth_getTransactionReceipt)
plus Etherscan-compatible REST API for historical address queries.
Includes confirmation freshness accounting and short-TTL rate-limit resilience.
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

logger = logging.getLogger("sentinel.adapters.evm")


class EvmAdapter(ChainAdapter):
    """EVM-compatible chain adapter supporting live JSON-RPC and Etherscan queries
    with automatic fallback to FixtureAdapter for offline-first resilience.
    """

    def __init__(
        self,
        chain: str = "ETH",
        rpc_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.chain = chain.upper()
        self.rpc_url = rpc_url or settings.EVM_RPC_URL or settings.ETH_RPC_URL
        self.api_key = api_key or settings.ETHERSCAN_API_KEY
        self.fixture_adapter = FixtureAdapter()

    def _rpc_call(self, method: str, params: list) -> Optional[Any]:
        """Perform a JSON-RPC call against EVM_RPC_URL."""
        if not self.rpc_url:
            return None
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": method,
                "params": params,
            }
            resp = httpx.post(self.rpc_url, json=payload, timeout=6.0)
            if resp.status_code == 200:
                result = resp.json().get("result")
                return result
        except Exception as e:
            logger.debug(f"EVM RPC call '{method}' failed: {e}")
        return None

    def get_latest_block_number(self) -> Optional[int]:
        """Fetch the current block number via eth_blockNumber."""
        res = self._rpc_call("eth_blockNumber", [])
        if res and isinstance(res, str):
            try:
                return int(res, 16)
            except ValueError:
                pass
        return None

    def get_transaction_by_hash(self, tx_hash: str, chain: Optional[str] = None) -> Optional[NormalizedTransaction]:
        """Read a transaction directly from an EVM node by its hash (within minutes of broadcast).
        Computes confirmation count and flags low confirmation (< 3).
        """
        clean_hash = tx_hash.strip()
        target_chain = (chain or self.chain).upper()
        cache_key = f"evm:tx:{clean_hash.lower()}"

        # 1. Check in-memory cache
        cached = adapter_cache.get(cache_key)
        if cached and not cached[1]:  # not stale
            return cached[0]

        # 2. Query direct JSON-RPC node
        if self.rpc_url:
            raw_tx = self._rpc_call("eth_getTransactionByHash", [clean_hash])
            if raw_tx and isinstance(raw_tx, dict):
                latest_block = self.get_latest_block_number()
                raw_block = raw_tx.get("blockNumber")
                tx_block = int(raw_block, 16) if raw_block else None
                is_pending = tx_block is None

                confirmations = None
                if tx_block is not None and latest_block is not None:
                    confirmations = max(0, latest_block - tx_block + 1)
                elif is_pending:
                    confirmations = 0

                low_conf = (confirmations is not None and confirmations < settings.CONFIRMATION_THRESHOLD) or is_pending

                val_hex = raw_tx.get("value", "0x0")
                try:
                    val_wei = int(val_hex, 16)
                except ValueError:
                    val_wei = 0
                val_eth = val_wei / 1e18

                # Fetch receipt for gas used
                receipt = self._rpc_call("eth_getTransactionReceipt", [clean_hash])
                gas_used = int(receipt.get("gasUsed", "0x0"), 16) if receipt and isinstance(receipt, dict) else None

                norm_tx = NormalizedTransaction(
                    tx_hash=raw_tx.get("hash", clean_hash),
                    chain=target_chain,
                    from_address=raw_tx.get("from", ""),
                    to_address=raw_tx.get("to") or "",
                    value=val_eth,
                    value_inr=val_eth * 250000.0,
                    timestamp=datetime.now(timezone.utc),
                    block_number=tx_block,
                    confirmations=confirmations,
                    is_pending=is_pending,
                    low_confirmation=low_conf,
                    is_stale=False,
                    metadata={"gas_used": gas_used, "source": "evm_rpc"},
                )
                adapter_cache.set(cache_key, norm_tx, has_low_confirmation=low_conf)
                return norm_tx

        # 3. Fallback to cached entry if available (even if expired)
        if cached:
            stale_tx = cached[0]
            stale_tx.is_stale = True
            return stale_tx

        # 4. Check fixture dataset
        for scenario in self.fixture_adapter.dataset.get("scenarios", []):
            for path in scenario.get("paths", []):
                if path.get("tx_hash", "").lower() == clean_hash.lower():
                    return NormalizedTransaction(
                        tx_hash=path.get("tx_hash"),
                        chain=path.get("chain", "ETH"),
                        from_address=path.get("from_addr"),
                        to_address=path.get("to_addr"),
                        value=float(path.get("value", 0)),
                        value_inr=float(path.get("value", 0)) * 250000.0,
                        timestamp=datetime.now(timezone.utc),
                        confirmations=12,
                        is_pending=False,
                        low_confirmation=False,
                        metadata={"source": "fixture_fallback"},
                    )

        return None

    def get_transactions(self, address: str, chain: Optional[str] = None) -> List[NormalizedTransaction]:
        target_chain = (chain or self.chain).upper()
        cache_key = f"evm:txs:{target_chain}:{address.lower()}"

        # Check Cache
        cached = adapter_cache.get(cache_key)
        if cached and not cached[1]:
            return cached[0]

        # If no live keys/RPC are provided, cleanly fallback to FixtureAdapter
        if not self.api_key and not self.rpc_url:
            logger.debug("No EVM provider keys configured. Falling back to FixtureAdapter.")
            return self.fixture_adapter.get_transactions(address, target_chain)

        latest_block = self.get_latest_block_number()

        # Attempt live Etherscan-compatible account query if API key is present
        if self.api_key:
            try:
                base_url = "https://api.etherscan.io/api"
                if target_chain == "POLYGON":
                    base_url = "https://api.polygonscan.com/api"
                elif target_chain == "ARBITRUM":
                    base_url = "https://api.arbiscan.io/api"
                elif target_chain == "BSC":
                    base_url = "https://api.bscscan.com/api"

                params = {
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": 50,
                    "sort": "desc",
                    "apikey": self.api_key,
                }
                resp = httpx.get(base_url, params=params, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "1" and isinstance(data.get("result"), list):
                        txs: List[NormalizedTransaction] = []
                        has_low_conf = False
                        for raw in data["result"]:
                            val = float(raw.get("value", 0)) / 1e18
                            ts_int = int(raw.get("timeStamp", 0))
                            ts = datetime.fromtimestamp(ts_int, tz=timezone.utc)
                            blk = int(raw.get("blockNumber", 0))

                            confs = None
                            if latest_block and blk > 0:
                                confs = max(0, latest_block - blk + 1)
                            else:
                                confs = int(raw.get("confirmations", 10))

                            low_conf = confs < settings.CONFIRMATION_THRESHOLD
                            if low_conf:
                                has_low_conf = True

                            txs.append(
                                NormalizedTransaction(
                                    tx_hash=raw.get("hash"),
                                    chain=target_chain,
                                    from_address=raw.get("from"),
                                    to_address=raw.get("to") or "",
                                    value=val,
                                    value_inr=val * 250000.0,
                                    timestamp=ts,
                                    block_number=blk,
                                    confirmations=confs,
                                    is_pending=confs == 0,
                                    low_confirmation=low_conf,
                                    is_sweep=False,
                                    metadata={"gas_used": raw.get("gasUsed"), "source": "etherscan"},
                                )
                            )
                        if txs:
                            adapter_cache.set(cache_key, txs, has_low_confirmation=has_low_conf)
                            return txs
            except Exception as e:
                logger.warning(f"EVM live query failed ({e}). Checking stale cache or fixture.")
                if cached:
                    stale_txs = cached[0]
                    for t in stale_txs:
                        t.is_stale = True
                    return stale_txs

        # Fallback to fixture adapter
        return self.fixture_adapter.get_transactions(address, target_chain)


# Alias for spec consistency
EvmLiveAdapter = EvmAdapter
