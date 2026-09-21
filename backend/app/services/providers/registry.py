"""Provider adapter registry and dispatcher.
Maps validated chain names to concrete ChainAdapter instances.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

from typing import Dict

from app.services.providers.base import ChainAdapter
from app.services.providers.bitcoin import BitcoinAdapter
from app.services.providers.blockchair import BlockchairAdapter
from app.services.providers.cardano import CardanoAdapter
from app.services.providers.evm import EvmProviderAdapter
from app.services.providers.monero import MoneroAdapter
from app.services.providers.solana import SolanaAdapter
from app.services.providers.stellar import StellarAdapter
from app.services.providers.tron import TronProviderAdapter
from app.services.providers.xrp import XrpAdapter
from app.services.providers.unsupported import UnsupportedLookupAdapter

_ADAPTER_INSTANCES: Dict[str, ChainAdapter] = {}


def get_provider_adapter(chain_name: str) -> ChainAdapter:
    """Returns the ChainAdapter for a given chain identifier."""
    c = chain_name.strip().lower()

    if c in _ADAPTER_INSTANCES:
        return _ADAPTER_INSTANCES[c]

    adapter: ChainAdapter
    if c == "bitcoin":
        adapter = BitcoinAdapter()
    elif c == "tron":
        adapter = TronProviderAdapter()
    elif c == "solana":
        adapter = SolanaAdapter()
    elif c in ("xrp_ledger", "xrp", "ripple"):
        adapter = XrpAdapter()
    elif c == "stellar":
        adapter = StellarAdapter()
    elif c in ("ethereum", "polygon", "arbitrum", "optimism", "bsc", "base", "avalanche"):
        adapter = EvmProviderAdapter(chain_key=c)
    elif c in ("litecoin", "dogecoin", "dash", "zcash", "bitcoin_cash"):
        adapter = BlockchairAdapter(chain_key=c)
    elif c == "cardano":
        adapter = CardanoAdapter()
    elif c == "monero":
        adapter = MoneroAdapter()
    else:
        adapter = UnsupportedLookupAdapter(chain_name=c)

    _ADAPTER_INSTANCES[c] = adapter
    return adapter
