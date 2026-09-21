"""Chain adapter abstract base interface and normalized transaction schema.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class NormalizedTransaction(BaseModel):
    """Canonical transaction model across all blockchain networks (EVM, TRON, BTC)."""
    tx_hash: str
    chain: str = "ETH"
    from_address: str
    to_address: str
    value: float
    value_inr: Optional[float] = None
    timestamp: datetime
    block_number: Optional[int] = None
    is_sweep: bool = False
    confirmations: Optional[int] = None
    is_pending: bool = False
    low_confirmation: bool = False  # True if confirmations < threshold or is_pending
    is_stale: bool = False          # True if served from stale cache on provider failure
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ChainAdapter(ABC):
    """Abstract interface for blockchain data providers (Fixture, RPC, Etherscan, TronGrid, Mempool)."""

    @abstractmethod
    def get_transactions(self, address: str, chain: str) -> List[NormalizedTransaction]:
        """Return a normalized list of transactions for a given wallet address and chain.
        Both incoming and outgoing transactions may be returned, with outgoing transactions
        typically used for hop progression.
        """
        pass

    def get_transaction_by_hash(self, tx_hash: str, chain: Optional[str] = None) -> Optional[NormalizedTransaction]:
        """Return a single normalized transaction by its transaction hash, or None if not found."""
        return None
