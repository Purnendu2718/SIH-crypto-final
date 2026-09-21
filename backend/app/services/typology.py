"""Rule-based money laundering typology detectors.
Detects Fan-Out, Peeling Chain, Privacy Mixers, and Layering over trace paths.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import TypologyDetected, TracePath, generate_uuid
from app.services.adapters import get_adapter


class TypologyHit:
    def __init__(
        self,
        typology: str,
        hop_start: int,
        hop_end: int,
        description: str,
        severity: str = "HIGH",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.typology = typology  # FAN_OUT, PEELING_CHAIN, MIXER, LAYERING
        self.hop_start = hop_start
        self.hop_end = hop_end
        self.description = description
        self.severity = severity  # CRITICAL, HIGH, MEDIUM
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "typology": self.typology,
            "hop_start": self.hop_start,
            "hop_end": self.hop_end,
            "description": self.description,
            "severity": self.severity,
            "details": self.details,
        }


class TypologyEngine:
    """Detects money laundering typologies across traced transaction paths."""

    def __init__(self, adapter=None):
        self.adapter = adapter or get_adapter()

    def detect_typologies(
        self,
        run_id: str,
        paths: List[TracePath],
        attributed_category: Optional[str] = None,
        attributed_entity: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> List[TypologyHit]:
        """Analyze trace paths and return list of flagged typologies, augmented by GraphSense categories."""
        hits: List[TypologyHit] = []

        # 0. Direct Category-based Typology Flags (Phase 8E)
        norm_cat = (attributed_category or "").lower()
        if norm_cat in ("mixing_service", "mixer"):
            hits.append(
                TypologyHit(
                    typology="MIXER",
                    hop_start=len(paths) if paths else 0,
                    hop_end=len(paths) if paths else 0,
                    description=f"Direct attribution to verified privacy mixer ({attributed_entity or 'Mixing Service'}).",
                    severity="CRITICAL",
                    details={"entity": attributed_entity, "category": attributed_category},
                )
            )
        elif norm_cat in ("dark_web", "darknet_market", "drugs", "weapons"):
            hits.append(
                TypologyHit(
                    typology="ILLICIT_SERVICE",
                    hop_start=len(paths) if paths else 0,
                    hop_end=len(paths) if paths else 0,
                    description=f"Direct attribution to illicit marketplace / dark web entity ({attributed_entity}).",
                    severity="CRITICAL",
                    details={"entity": attributed_entity, "category": attributed_category},
                )
            )
        elif norm_cat in ("ransomware", "phishing", "hacking", "service_hack"):
            hits.append(
                TypologyHit(
                    typology="CYBERCRIME_ACTOR",
                    hop_start=len(paths) if paths else 0,
                    hop_end=len(paths) if paths else 0,
                    description=f"Transaction identified as cybercrime/exploiter entity ({attributed_entity}).",
                    severity="CRITICAL",
                    details={"entity": attributed_entity, "category": attributed_category},
                )
            )
        elif norm_cat in ("defi", "defi_dex", "defi_lending", "defi_bridge"):
            hits.append(
                TypologyHit(
                    typology="DEFI_INTERACTION",
                    hop_start=len(paths) if paths else 0,
                    hop_end=len(paths) if paths else 0,
                    description=f"Interaction with decentralized protocol ({attributed_entity}) used for liquidity/swapping.",
                    severity="HIGH",
                    details={"entity": attributed_entity, "category": attributed_category},
                )
            )

        if not paths:
            return hits

        # 1. FAN_OUT Detection
        # Check if the starting address or any hop address splits funds to 2+ destinations
        start_addr = paths[0].from_addr
        start_txs = self.adapter.get_transactions(start_addr, paths[0].chain)
        start_outgoing = [tx for tx in start_txs if tx.from_address.lower() == start_addr.lower()]

        if len(start_outgoing) >= 2:
            destinations = list({tx.to_address for tx in start_outgoing})
            hits.append(
                TypologyHit(
                    typology="FAN_OUT",
                    hop_start=1,
                    hop_end=1,
                    description=f"Suspect address rapidly dispersed funds across {len(destinations)} concurrent recipient wallets.",
                    severity="HIGH",
                    details={"destinations": destinations, "count": len(destinations)},
                )
            )

        # 2. MIXER Detection
        # Check if any path destination touches a mixer contract or mixer relayer
        mixer_keywords = ["mixer", "tornadocash", "railgun", "tumbler", "blender"]
        for p in paths:
            addr_lower = (p.to_addr or "").lower()
            # Don't add duplicate MIXER if already added from category
            if any(k in addr_lower for k in mixer_keywords) and not any(h.typology == "MIXER" for h in hits):
                hits.append(
                    TypologyHit(
                        typology="MIXER",
                        hop_start=p.hop_index,
                        hop_end=p.hop_index + 1 if p.hop_index < len(paths) else p.hop_index,
                        description=f"Funds routed through privacy mixer or obfuscation contract at hop {p.hop_index}.",
                        severity="CRITICAL",
                        details={"contract_or_relayer": p.to_addr, "tx_hash": p.tx_hash},
                    )
                )

        # 3. PEELING_CHAIN Detection
        # Successive hops (>= 4 hops) where funds incrementally peel off with descending values
        if len(paths) >= 4:
            is_peeling = True
            for i in range(len(paths) - 1):
                val_curr = float(paths[i].value) if paths[i].value else 0.0
                val_next = float(paths[i + 1].value) if paths[i + 1].value else 0.0
                if val_next >= val_curr:
                    is_peeling = False
                    break

            if is_peeling:
                hits.append(
                    TypologyHit(
                        typology="PEELING_CHAIN",
                        hop_start=1,
                        hop_end=len(paths),
                        description=f"Continuous peeling chain detected across {len(paths)} consecutive hops with systematic balance reduction.",
                        severity="HIGH",
                        details={"total_hops": len(paths)},
                    )
                )

        # 4. LAYERING Detection
        # Triggered by multi-hop routing (>= 3 hops) or cross-chain bridge interaction
        chains_seen = {p.chain for p in paths}
        has_bridge = any("bridge" in (p.to_addr or "").lower() for p in paths) or len(chains_seen) > 1

        if has_bridge or len(paths) >= 3:
            desc = "Multi-hop structuring and cross-chain bridge layering" if has_bridge else f"Multi-hop layering across {len(paths)} hops"
            hits.append(
                TypologyHit(
                    typology="LAYERING",
                    hop_start=1,
                    hop_end=len(paths),
                    description=f"{desc} designed to obfuscate transaction provenance.",
                    severity="HIGH" if has_bridge else "MEDIUM",
                    details={"chains": list(chains_seen), "cross_chain": has_bridge},
                )
            )

        # Persist to database if session provided
        if db is not None:
            for hit in hits:
                record = TypologyDetected(
                    id=generate_uuid(),
                    run_id=run_id,
                    typology=hit.typology,
                    hop_start=hit.hop_start,
                    hop_end=hit.hop_end,
                )
                db.add(record)
            db.commit()

        return hits
