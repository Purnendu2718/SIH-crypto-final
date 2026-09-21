"""Bounded Breadth-First Search / Shortest-Path-to-Off-Ramp Trace Engine.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AnalysisRun,
    TracePath,
    VASPDirectory,
    EntityLabel,
    generate_uuid,
    utc_now,
)
from app.services.adapters.base import ChainAdapter, NormalizedTransaction
from app.services.adapters import get_adapter


class ForensicStatus(str):
    """String status supporting Phase 8C 4-state integrity while maintaining backward compatibility."""

    def __eq__(self, other):
        if not isinstance(other, str):
            return False
        val = str(self)
        other_str = str(other)
        if val == other_str:
            return True
        if val == "ANALYSIS_COMPLETE_ATTRIBUTED" and other_str == "COMPLETED":
            return True
        if val == "ANALYSIS_COMPLETE_NO_PATH_FOUND" and other_str in ("NO_CONFIDENT_OFF_RAMP", "COMPLETED_NO_OFFRAMP"):
            return True
        return False

    __hash__ = str.__hash__



class TraceResult:
    """Structured result of a trace engine run."""

    def __init__(
        self,
        run_id: str,
        status: str,
        total_hops: int,
        paths: List[TracePath],
        matched_entity: Optional[str] = None,
        matched_hot_wallet: Optional[str] = None,
        visited_addresses: Optional[List[str]] = None,
    ):
        self.run_id = run_id
        self.status = status
        self.total_hops = total_hops
        self.paths = paths
        self.matched_entity = matched_entity
        self.matched_hot_wallet = matched_hot_wallet
        self.visited_addresses = visited_addresses or []

    def to_dict(self) -> Dict[str, Any]:
        has_low_conf = any(getattr(p, "low_confirmation", False) for p in self.paths)
        return {
            "run_id": self.run_id,
            "status": self.status,
            "total_hops": self.total_hops,
            "matched_entity": self.matched_entity,
            "matched_hot_wallet": self.matched_hot_wallet,
            "visited_addresses": self.visited_addresses,
            "has_low_confirmation_hops": has_low_conf,
            "paths": [
                {
                    "hop_index": p.hop_index,
                    "from_addr": p.from_addr,
                    "to_addr": p.to_addr,
                    "tx_hash": p.tx_hash,
                    "chain": p.chain,
                    "value": float(p.value) if p.value is not None else 0.0,
                    "confirmations": getattr(p, "confirmations", None),
                    "low_confirmation": getattr(p, "low_confirmation", False),
                }
                for p in self.paths
            ],
        }


class TraceEngine:
    """Forensic multi-hop trace engine.
    Follows dominant-value outgoing flows, filters dust, respects hop budgets,
    and terminates early upon encountering a known VASP hot wallet.
    """

    def __init__(
        self,
        max_hops: int = 15,
        dust_threshold: float = 0.001,
        adapter: Optional[ChainAdapter] = None,
    ):
        self.max_hops = max_hops
        self.dust_threshold = dust_threshold
        self.adapter = adapter or get_adapter()

    def _get_vasp_hot_wallet_map(self, db: Optional[Session] = None) -> Dict[str, str]:
        """Build a lookup map of {hot_wallet_address: entity_name}.
        Preserves exact casing for case-sensitive chains (BTC, TRON) and indexes lowercase for EVM hex.
        """
        hot_wallet_map: Dict[str, str] = {}

        if db is not None:
            # 1. Local EntityLabels from GraphSense TagPacks (Phase 8E)
            try:
                label_rows = db.query(EntityLabel).all()
                for el in label_rows:
                    clean_a = el.address.strip()
                    hot_wallet_map[clean_a] = el.label
                    if clean_a.startswith(('0x', '0X')):
                        hot_wallet_map[clean_a.lower()] = el.label
            except Exception:
                pass

            # 2. VASPDirectory rows (legacy seed)
            vasp_rows = db.query(VASPDirectory).all()
            for vasp in vasp_rows:
                addrs = vasp.hot_wallet_addresses or []
                for a in addrs:
                    clean_a = a.strip()
                    hot_wallet_map[clean_a] = vasp.entity_name
                    if clean_a.startswith(('0x', '0X')):
                        hot_wallet_map[clean_a.lower()] = vasp.entity_name

        # Supplement with adapter directory
        if hasattr(self.adapter, "get_vasp_directory"):
            for vasp_data in self.adapter.get_vasp_directory():
                for a in vasp_data.get("hot_wallet_addresses", []):
                    clean_a = a.strip()
                    hot_wallet_map[clean_a] = vasp_data.get("entity_name", "Unknown VASP")
                    if clean_a.startswith(('0x', '0X')):
                        hot_wallet_map[clean_a.lower()] = vasp_data.get("entity_name", "Unknown VASP")

        return hot_wallet_map

    def execute_trace(
        self,
        start_address: str,
        initial_chain: str = "ETH",
        run_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> TraceResult:
        """Execute bounded BFS following dominant-value outgoing transactions.
        Persists resulting trace_paths to the database.
        """
        active_run_id = run_id or generate_uuid()
        vasp_hot_wallets = self._get_vasp_hot_wallet_map(db)

        current_addr = start_address.strip()
        current_chain = initial_chain.strip().upper()

        visited_addresses: List[str] = [current_addr]
        persisted_paths: List[TracePath] = []
        hop_index = 1
        matched_entity: Optional[str] = None
        matched_hot_wallet: Optional[str] = None

        # Check if start address itself is already an off-ramp (0-hop direct root attribution)
        root_matched_entity = vasp_hot_wallets.get(current_addr)
        if not root_matched_entity and current_addr.startswith(('0x', '0X')):
            root_matched_entity = vasp_hot_wallets.get(current_addr.lower())

        if not root_matched_entity and settings.LIVE_MODE:
            try:
                from app.services.graphsense_client import GraphSenseClient
                gs_client = GraphSenseClient()
                gs_match = gs_client.lookup_address_entity(address=current_addr, chain=current_chain)
                if gs_match:
                    root_matched_entity = gs_match["entity_name"]
            except Exception:
                pass

        if root_matched_entity:
            matched_entity = root_matched_entity
            matched_hot_wallet = current_addr
            status = ForensicStatus("ANALYSIS_COMPLETE_ATTRIBUTED")
            # CRITICAL: Persist run status and completion timestamp to the database
            if db is not None:
                run = db.query(AnalysisRun).filter(AnalysisRun.run_id == active_run_id).first()
                if run:
                    run.status = status
                    run.completed_at = utc_now()
                db.commit()

            return TraceResult(
                run_id=active_run_id,
                status=status,
                total_hops=0,
                paths=[],
                matched_entity=matched_entity,
                matched_hot_wallet=matched_hot_wallet,
                visited_addresses=visited_addresses,
            )

        # Hop traversal loop up to max_hops budget
        while hop_index <= self.max_hops:
            txs: List[NormalizedTransaction] = self.adapter.get_transactions(current_addr, current_chain)

            # Filter outgoing transactions from current_addr
            outgoing = [
                tx for tx in txs
                if tx.from_address.strip().lower() == current_addr.lower()
                and tx.value >= self.dust_threshold
            ]

            if not outgoing:
                # No more outgoing transactions found along this path
                break

            # Follow dominant-value outgoing transaction at this hop
            dominant_tx = max(outgoing, key=lambda t: t.value)

            # Create and stage TracePath model
            path_entry = TracePath(
                id=generate_uuid(),
                run_id=active_run_id,
                hop_index=hop_index,
                from_addr=dominant_tx.from_address,
                to_addr=dominant_tx.to_address,
                tx_hash=dominant_tx.tx_hash,
                chain=dominant_tx.chain,
                value=dominant_tx.value,
                confirmations=dominant_tx.confirmations,
                low_confirmation=dominant_tx.low_confirmation,
            )
            persisted_paths.append(path_entry)
            if db is not None:
                db.add(path_entry)

            # Advance to destination address
            current_addr = dominant_tx.to_address.strip()
            visited_addresses.append(current_addr)
            current_chain = dominant_tx.chain.upper()

            # Handle cross-chain bridge targets (e.g. Stargate, Multichain)
            if dominant_tx.metadata.get("cross_chain_target"):
                current_chain = dominant_tx.metadata["cross_chain_target"].upper()

            # Check if destination matches a known VASP hot wallet or entity label
            dest_match = vasp_hot_wallets.get(current_addr)
            if not dest_match and current_addr.startswith(('0x', '0X')):
                dest_match = vasp_hot_wallets.get(current_addr.lower())

            if not dest_match and settings.LIVE_MODE:
                try:
                    from app.services.graphsense_client import GraphSenseClient
                    gs_client = GraphSenseClient()
                    gs_match = gs_client.lookup_address_entity(address=current_addr, chain=current_chain)
                    if gs_match:
                        dest_match = gs_match["entity_name"]
                except Exception:
                    pass

            if dest_match:
                matched_entity = dest_match
                matched_hot_wallet = current_addr
                break

            # Increment hop counter
            hop_index += 1

        # Determine run status: ANALYSIS_COMPLETE_ATTRIBUTED if VASP found, else ANALYSIS_COMPLETE_NO_PATH_FOUND
        if matched_entity:
            status = ForensicStatus("ANALYSIS_COMPLETE_ATTRIBUTED")
        else:
            status = ForensicStatus("ANALYSIS_COMPLETE_NO_PATH_FOUND")

        # Update AnalysisRun in database if run exists
        if db is not None:
            run = db.query(AnalysisRun).filter(AnalysisRun.run_id == active_run_id).first()
            if run:
                run.status = status
                run.completed_at = utc_now()
            db.commit()

        return TraceResult(
            run_id=active_run_id,
            status=status,
            total_hops=len(persisted_paths),
            paths=persisted_paths,
            matched_entity=matched_entity,
            matched_hot_wallet=matched_hot_wallet,
            visited_addresses=visited_addresses,
        )


def trace_wallet_submission(
    submission_id: str,
    db: Session,
    max_hops: int = 15,
    dust_threshold: float = 0.001,
) -> TraceResult:
    """Helper to execute trace engine for a specific WalletSubmission database record."""
    from app.models import WalletSubmission

    submission = db.query(WalletSubmission).filter(WalletSubmission.submission_id == submission_id).first()
    if not submission:
        raise ValueError(f"WalletSubmission with ID '{submission_id}' not found.")

    # Find or create an AnalysisRun for this submission
    run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.submission_id == submission_id, AnalysisRun.status == "PENDING")
        .first()
    )
    if not run:
        run = AnalysisRun(
            run_id=generate_uuid(),
            submission_id=submission_id,
            status="PENDING",
            started_at=utc_now(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

    engine = TraceEngine(max_hops=max_hops, dust_threshold=dust_threshold)
    return engine.execute_trace(
        start_address=submission.address,
        initial_chain=submission.chain,
        run_id=run.run_id,
        db=db,
    )
