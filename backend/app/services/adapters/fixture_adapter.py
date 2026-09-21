"""Offline fixture adapter reading from demo_dataset.json.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.services.adapters.base import ChainAdapter, NormalizedTransaction

FIXTURE_FILE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "fixtures",
    "demo_dataset.json",
)


class FixtureAdapter(ChainAdapter):
    """Concrete chain adapter providing seeded offline-first forensic transactions."""

    def __init__(self, fixture_path: str = FIXTURE_FILE_PATH):
        self.fixture_path = fixture_path
        self._dataset: Dict[str, Any] = {}
        self._load_dataset()

    def _load_dataset(self):
        """Load fixture JSON file from disk."""
        if not os.path.exists(self.fixture_path):
            raise FileNotFoundError(f"Fixture dataset not found at: {self.fixture_path}")
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            self._dataset = json.load(f)

    @property
    def dataset(self) -> Dict[str, Any]:
        """Expose underlying dataset dictionary."""
        return self._dataset

    def get_vasp_directory(self) -> List[Dict[str, Any]]:
        """Return the seeded Indian VASP directory."""
        return self._dataset.get("vasp_directory", [])

    def is_vasp_hot_wallet(self, address: str, chain: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Check if an address matches any known VASP hot wallet.
        Returns the VASP entity metadata or None.
        """
        addr_clean = address.strip().lower()
        for vasp in self.get_vasp_directory():
            for hot_addr in vasp.get("hot_wallet_addresses", []):
                if hot_addr.strip().lower() == addr_clean:
                    return vasp
        return None

    def get_scenarios(self) -> List[Dict[str, Any]]:
        """Return all scenario definitions."""
        return self._dataset.get("scenarios", [])

    def get_scenario_by_id(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Find a scenario by its identifier."""
        for sc in self.get_scenarios():
            if sc.get("id") == scenario_id:
                return sc
        return None

    def get_scenario_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Find the scenario associated with a suspect or intermediary address."""
        addr_clean = address.strip().lower()
        for sc in self.get_scenarios():
            if sc.get("suspect_address", "").strip().lower() == addr_clean:
                return sc
            for tx in sc.get("transactions", []):
                if tx["from_address"].strip().lower() == addr_clean or tx["to_address"].strip().lower() == addr_clean:
                    return sc
        return None

    def get_transactions(self, address: str, chain: str) -> List[NormalizedTransaction]:
        """Fetch all normalized transactions involving the specified address.
        Supports case-insensitive address matching and cross-chain bridge hops.
        """
        addr_clean = address.strip().lower()
        matched: List[NormalizedTransaction] = []

        for scenario in self.get_scenarios():
            for raw_tx in scenario.get("transactions", []):
                tx_from = raw_tx["from_address"].strip().lower()
                tx_to = raw_tx["to_address"].strip().lower()
                tx_chain = raw_tx.get("chain", "ETH").upper()

                # Match if address is sender or receiver on chain (or bridge transfer)
                if tx_from == addr_clean or tx_to == addr_clean:
                    # Parse timestamp
                    ts_str = raw_tx["timestamp"]
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    ts = datetime.fromisoformat(ts_str)

                    matched.append(
                        NormalizedTransaction(
                            tx_hash=raw_tx["tx_hash"],
                            chain=tx_chain,
                            from_address=raw_tx["from_address"],
                            to_address=raw_tx["to_address"],
                            value=float(raw_tx["value"]),
                            value_inr=float(raw_tx.get("value_inr", 0.0)) if raw_tx.get("value_inr") else None,
                            timestamp=ts,
                            block_number=raw_tx.get("block_number"),
                            is_sweep=bool(raw_tx.get("is_sweep", False)),
                            metadata=raw_tx.get("metadata", {}),
                        )
                    )

        return matched
