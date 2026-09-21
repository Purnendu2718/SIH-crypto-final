"""Blockchain adapter interfaces and concrete implementations.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8.
"""

from app.config import settings
from app.services.adapters.base import ChainAdapter, NormalizedTransaction
from app.services.adapters.fixture_adapter import FixtureAdapter
from app.services.adapters.evm_adapter import EvmAdapter, EvmLiveAdapter
from app.services.adapters.tron_adapter import TronAdapter, TronLiveAdapter
from app.services.adapters.btc_adapter import BtcAdapter, BtcLiveAdapter

# Singleton instances
_default_fixture_adapter = FixtureAdapter()
_default_evm_adapter = EvmAdapter()
_default_tron_adapter = TronAdapter()
_default_btc_adapter = BtcAdapter()


def get_adapter(chain: str = "ETH") -> ChainAdapter:
    """Factory function returning the active chain adapter for the given network.
    Air-gapped safety: If LIVE_MODE is False (default), returns FixtureAdapter exclusively
    with zero outbound network requests.
    When LIVE_MODE is True, returns live adapter with automated Fixture fallback on error.
    """
    if not settings.LIVE_MODE:
        return _default_fixture_adapter

    c = chain.upper()
    if c == "TRON":
        return _default_tron_adapter
    elif c in ("BTC", "BITCOIN"):
        return _default_btc_adapter
    elif c in ("ETH", "ETHEREUM", "POLYGON", "ARBITRUM", "BSC"):
        return _default_evm_adapter
    return _default_fixture_adapter


__all__ = [
    "ChainAdapter",
    "NormalizedTransaction",
    "FixtureAdapter",
    "EvmAdapter",
    "EvmLiveAdapter",
    "TronAdapter",
    "TronLiveAdapter",
    "BtcAdapter",
    "BtcLiveAdapter",
    "get_adapter",
]
