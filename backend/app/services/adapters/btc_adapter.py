"""Bitcoin Blockchain Live Adapter (Mempool.space / Blockstream Esplora REST API).
Directly surfaces unconfirmed mempool transactions and minute-old Bitcoin transfers
with confirmation freshness tracking and short-TTL cache resilience.
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

logger = logging.getLogger("sentinel.adapters.btc")


class BtcAdapter(ChainAdapter):
    """Bitcoin chain adapter utilizing mempool.space / Esplora REST APIs
    to rapidly detect unconfirmed mempool and recently settled transactions.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
    ):
        self.chain = "BTC"
        self.api_url = (api_url or settings.MEMPOOL_API_URL or "https://mempool.space/api").rstrip("/")
        self.fixture_adapter = FixtureAdapter()

    def get_tip_height(self) -> Optional[int]:
        """Get current tip block height from mempool.space."""
        try:
            resp = httpx.get(f"{self.api_url}/blocks/tip/height", timeout=4.0)
            if resp.status_code == 200:
                return int(resp.text.strip())
        except Exception:
            pass
        return None

    def get_transaction_by_hash(self, tx_hash: str, chain: Optional[str] = "BTC") -> Optional[NormalizedTransaction]:
        """Fetch a Bitcoin transaction by txid from mempool.space."""
        clean_hash = tx_hash.strip()
        cache_key = f"btc:tx:{clean_hash.lower()}"

        cached = adapter_cache.get(cache_key)
        if cached and not cached[1]:
            return cached[0]

        try:
            url = f"{self.api_url}/tx/{clean_hash}"
            resp = httpx.get(url, timeout=5.0)
            if resp.status_code == 200:
                raw = resp.json()
                txid = raw.get("txid", clean_hash)
                status_obj = raw.get("status", {})
                is_confirmed = status_obj.get("confirmed", False)
                block_height = status_obj.get("block_height")

                confirmations = 0
                if is_confirmed and block_height:
                    tip = self.get_tip_height()
                    if tip:
                        confirmations = max(1, tip - block_height + 1)
                    else:
                        confirmations = 6
                else:
                    confirmations = 0

                low_conf = not is_confirmed or confirmations < settings.CONFIRMATION_THRESHOLD

                # Determine primary from_address and to_address
                vin = raw.get("vin", [])
                from_addr = "N/A"
                if vin and vin[0].get("prevout"):
                    from_addr = vin[0]["prevout"].get("scriptpubkey_address", "N/A")

                vout = raw.get("vout", [])
                to_addr = ""
                total_sats = 0
                outputs_list = []
                for out in vout:
                    addr = out.get("scriptpubkey_address")
                    sats = out.get("value", 0)
                    total_sats += sats
                    if addr:
                        outputs_list.append({"address": addr, "value_sats": sats})
                        if not to_addr and addr != from_addr:
                            to_addr = addr

                if not to_addr and outputs_list:
                    to_addr = outputs_list[0]["address"]

                btc_val = total_sats / 1e8
                block_time = status_obj.get("block_time")
                ts = datetime.fromtimestamp(block_time, tz=timezone.utc) if block_time else datetime.now(timezone.utc)

                norm_tx = NormalizedTransaction(
                    tx_hash=txid,
                    chain="BTC",
                    from_address=from_addr,
                    to_address=to_addr,
                    value=btc_val,
                    value_inr=btc_val * 7500000.0,  # ~ ₹75 Lakhs per BTC
                    timestamp=ts,
                    block_number=block_height,
                    confirmations=confirmations,
                    is_pending=not is_confirmed,
                    low_confirmation=low_conf,
                    is_stale=False,
                    metadata={"outputs": outputs_list, "source": "mempool_space"},
                )
                adapter_cache.set(cache_key, norm_tx, has_low_confirmation=low_conf)
                return norm_tx
        except Exception as e:
            logger.debug(f"mempool.space tx lookup failed: {e}")
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
                        chain=path.get("chain", "BTC"),
                        from_address=path.get("from_addr"),
                        to_address=path.get("to_addr"),
                        value=float(path.get("value", 0)),
                        value_inr=float(path.get("value", 0)) * 7500000.0,
                        timestamp=datetime.now(timezone.utc),
                        confirmations=6,
                        is_pending=False,
                        low_confirmation=False,
                        metadata={"source": "fixture_fallback"},
                    )
        return None

    def get_transactions(self, address: str, chain: Optional[str] = "BTC") -> List[NormalizedTransaction]:
        cache_key = f"btc:txs:{address.lower()}"

        cached = adapter_cache.get(cache_key)
        if cached and not cached[1]:
            return cached[0]

        try:
            url = f"{self.api_url}/address/{address}/txs"
            resp = httpx.get(url, timeout=6.0)
            if resp.status_code == 200:
                raw_txs = resp.json()
                tip = self.get_tip_height()
                txs: List[NormalizedTransaction] = []
                has_low_conf = False

                for raw in raw_txs:
                    txid = raw.get("txid", "")
                    status_obj = raw.get("status", {})
                    is_confirmed = status_obj.get("confirmed", False)
                    block_height = status_obj.get("block_height")

                    confirmations = 0
                    if is_confirmed and block_height and tip:
                        confirmations = max(1, tip - block_height + 1)
                    elif is_confirmed:
                        confirmations = 6
                    else:
                        confirmations = 0

                    low_conf = not is_confirmed or confirmations < settings.CONFIRMATION_THRESHOLD
                    if low_conf:
                        has_low_conf = True

                    # Find recipient / destination
                    vout = raw.get("vout", [])
                    out_addr = ""
                    sats_val = 0
                    for out in vout:
                        sats_val += out.get("value", 0)
                        dest = out.get("scriptpubkey_address")
                        if dest and dest != address and not out_addr:
                            out_addr = dest
                    if not out_addr and vout:
                        out_addr = vout[0].get("scriptpubkey_address", address)

                    btc_val = sats_val / 1e8
                    block_time = status_obj.get("block_time")
                    ts = datetime.fromtimestamp(block_time, tz=timezone.utc) if block_time else datetime.now(timezone.utc)

                    txs.append(
                        NormalizedTransaction(
                            tx_hash=txid,
                            chain="BTC",
                            from_address=address,
                            to_address=out_addr,
                            value=btc_val,
                            value_inr=btc_val * 7500000.0,
                            timestamp=ts,
                            block_number=block_height,
                            confirmations=confirmations,
                            is_pending=not is_confirmed,
                            low_confirmation=low_conf,
                            is_sweep=False,
                            metadata={"source": "mempool_space"},
                        )
                    )
                if txs:
                    adapter_cache.set(cache_key, txs, has_low_confirmation=has_low_conf)
                    return txs
        except Exception as e:
            logger.warning(f"mempool.space address query failed ({e}). Checking cache or fixture.")
            if cached:
                stale_txs = cached[0]
                for t in stale_txs:
                    t.is_stale = True
                return stale_txs

        # Fallback to fixture adapter
        return self.fixture_adapter.get_transactions(address, "BTC")


# Alias for spec consistency
BtcLiveAdapter = BtcAdapter
