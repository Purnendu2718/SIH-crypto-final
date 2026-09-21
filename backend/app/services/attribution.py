"""Weighted Scoring Attribution Engine with 4-Tier Worldwide Coverage Hierarchy.
Order:
(a) Local entity_labels match (GraphSense TagPacks)
(b) Live GraphSense entity API match (api.ikna.io when LIVE_MODE=True)
(c) OFAC sanctions match (Phase 8D)
(d) CEX sweep-heuristic match (Phase 4 legacy / vasp_directory)
(e) Insufficient evidence

Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8E.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Attribution,
    TracePath,
    AnalysisRun,
    Entity,
    EntityLabel,
    SanctionsList,
    generate_uuid,
)


# Weighted scoring factors per solution proposal
WEIGHTS = {
    "sweep_label_match": 0.35,
    "path_proximity": 0.20,
    "deposit_pattern_similarity": 0.15,
    "temporal_correlation": 0.15,
    "co_spend_cluster": 0.10,
    "behavioral": 0.05,
}

CONFIDENCE_BANDS = {
    "VERY_HIGH": 0.85,
    "HIGH": 0.65,
    "MEDIUM": 0.40,
}

# Forensic category precedence mapping (higher value takes priority)
CATEGORY_PRIORITY = {
    "mixing_service": 100,
    "mixer": 100,
    "tumbler": 100,
    "darknet_market": 90,
    "dark_web": 90,
    "ransomware": 85,
    "scam": 80,
    "sanction": 80,
    "sanctions": 80,
    "sanctioned": 80,
    "illicit": 80,
    "terrorist_financing": 80,
    "defi_dex": 75,
    "dex": 75,
    "defi_lending": 70,
    "defi": 65,
    "exchange": 60,
    "p2p_exchange": 58,
    "custodial_wallet": 55,
    "payment_processor": 50,
    "gambling": 45,
    "mining_pool": 40,
    "mining_service": 40,
    "service": 30,
    "organization": 10,
}


def select_primary_category(cats: Optional[List[str]]) -> Optional[str]:
    """Select the most forensically relevant primary category from a list of tags."""
    if not cats:
        return None
    sorted_cats = sorted(
        cats,
        key=lambda c: CATEGORY_PRIORITY.get(c.lower().strip() if isinstance(c, str) else "", 20),
        reverse=True,
    )
    return sorted_cats[0]


def get_confidence_band(score: float) -> str:
    """Return explicit confidence band string."""
    if score >= CONFIDENCE_BANDS["VERY_HIGH"]:
        return "VERY_HIGH"
    elif score >= CONFIDENCE_BANDS["HIGH"]:
        return "HIGH"
    elif score >= CONFIDENCE_BANDS["MEDIUM"]:
        return "MEDIUM"
    else:
        return "INSUFFICIENT_EVIDENCE"


class AttributionResult:
    def __init__(
        self,
        run_id: str,
        matched_entity: str,
        rule_fired: str,
        confidence: float,
        confidence_band: str,
        score_breakdown: Dict[str, Any],
        attribution_source: Optional[str] = None,
        entity_category: Optional[str] = None,
        entity_categories: Optional[List[str]] = None,
    ):
        self.run_id = run_id
        self.matched_entity = matched_entity
        self.rule_fired = rule_fired
        self.confidence = confidence
        self.confidence_band = confidence_band
        self.score_breakdown = score_breakdown
        self.attribution_source = attribution_source
        self.entity_category = entity_category
        self.entity_categories = entity_categories or ([entity_category] if entity_category else [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "matched_entity": self.matched_entity,
            "rule_fired": self.rule_fired,
            "confidence": round(self.confidence, 4),
            "confidence_band": self.confidence_band,
            "score_breakdown": self.score_breakdown,
            "attribution_source": self.attribution_source,
            "entity_category": self.entity_category,
            "entity_categories": self.entity_categories,
        }


class AttributionEngine:
    """Computes explainable weighted attribution score according to the Phase 8E 4-tier hierarchy."""

    def compute_attribution(
        self,
        run_id: str,
        paths: List[TracePath],
        matched_entity: Optional[str] = None,
        matched_hot_wallet: Optional[str] = None,
        target_address: Optional[str] = None,
        chain: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> AttributionResult:
        """Evaluate attribution in strict priority order:
        (a) Local entity_labels match
        (b) Live GraphSense API match (if LIVE_MODE=True)
        (c) OFAC Sanctions match
        (d) CEX Sweep Heuristic match
        """
        hop_count = len(paths) if paths else 0

        # Determine target address to attribute
        if paths:
            candidate_addr = paths[-1].to_addr
            candidate_chain = paths[-1].chain
        else:
            candidate_addr = target_address or matched_hot_wallet
            candidate_chain = chain

        if not candidate_addr and matched_hot_wallet:
            candidate_addr = matched_hot_wallet

        clean_candidate = candidate_addr.strip() if candidate_addr else None

        # Burn / Null address filter (never attribute as exchange or off-ramp)
        if clean_candidate in ("0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dead", "0x0"):
            result = AttributionResult(
                run_id=run_id,
                matched_entity="Insufficient Evidence",
                rule_fired="NO_PATH_DETECTED",
                confidence=0.0,
                confidence_band="INSUFFICIENT_EVIDENCE",
                score_breakdown={
                    "factors": {},
                    "total_score": 0.0,
                    "reason": "Target address is an unspendable burn or null address.",
                },
                attribution_source="NO_PATH_DETECTED",
            )
            self._persist_attribution(result, db)
            return result

        # ======================================================================
        # Tier (a): Local entity_labels Match (GraphSense TagPacks)
        # ======================================================================
        if db is not None and clean_candidate:
            # Check exact and lower-case address match
            label_row = (
                db.query(EntityLabel)
                .filter(
                    (EntityLabel.address == clean_candidate)
                    | (EntityLabel.address == clean_candidate.lower())
                )
                .first()
            )
            if label_row:
                # Resolve associated Entity metadata
                entity_row = None
                if label_row.actor_id:
                    entity_row = db.query(Entity).filter(Entity.actor_id == label_row.actor_id).first()

                # Prioritize explicit investigator/VASP override if already passed, then label_row.label, then entity_row.label
                ent_label = matched_entity or label_row.label or (entity_row.label if entity_row else "Unknown Entity")
                cats = entity_row.categories if entity_row and entity_row.categories else []
                primary_cat = select_primary_category(cats)

                conf = 1.0 if hop_count <= 2 else max(0.65, round(1.0 - (hop_count * 0.05), 2))
                band = get_confidence_band(conf)
                attr_source = "ROOT_ADDRESS_IS_KNOWN_ENTITY" if hop_count == 0 else "LOCAL_ENTITY_LABELS"

                factors = {
                    "local_dataset_match": {
                        "weight": 0.40,
                        "score": 1.0,
                        "weighted": 0.40,
                        "description": f"Verified match in local TagPacks repository: {ent_label}",
                    },
                    "path_proximity": {
                        "weight": 0.30,
                        "score": 1.0 if hop_count <= 2 else 0.8,
                        "weighted": 0.30 if hop_count <= 2 else 0.24,
                        "description": f"Hop count {hop_count} proximity score",
                    },
                    "entity_verification": {
                        "weight": 0.30,
                        "score": 1.0,
                        "weighted": 0.30,
                        "description": f"Actor ID: {label_row.actor_id or 'N/A'}, Category: {primary_cat or 'N/A'}",
                    },
                }

                result = AttributionResult(
                    run_id=run_id,
                    matched_entity=ent_label,
                    rule_fired="LOCAL_ENTITY_LABEL_MATCH",
                    confidence=conf,
                    confidence_band=band,
                    score_breakdown={
                        "factors": factors,
                        "total_score": round(conf, 4),
                        "confidence_band": band,
                        "hop_count": hop_count,
                        "actor_id": label_row.actor_id,
                        "entity_category": primary_cat,
                        "categories": cats,
                        "source_url": label_row.source_url,
                        "tag_source": label_row.tag_source,
                    },
                    attribution_source=attr_source,
                    entity_category=primary_cat,
                    entity_categories=cats,
                )
                self._persist_attribution(result, db)
                return result

        # ======================================================================
        # Tier (b): Live GraphSense Entity API Match (api.ikna.io when LIVE_MODE=True)
        # ======================================================================
        if settings.LIVE_MODE and clean_candidate:
            try:
                from app.services.graphsense_client import GraphSenseClient
                gs_client = GraphSenseClient()
                lookup_chain = candidate_chain or chain or "ETH"
                gs_match = gs_client.lookup_address_entity(address=clean_candidate, chain=lookup_chain)
                if gs_match:
                    ent_label = gs_match["entity_name"]
                    cats = gs_match.get("categories", [])
                    primary_cat = select_primary_category(cats) or gs_match.get("category")
                    conf = 0.90 if hop_count <= 2 else max(0.60, round(0.90 - (hop_count * 0.05), 2))
                    band = get_confidence_band(conf)

                    factors = {
                        "live_graphsense_match": {
                            "weight": 0.40,
                            "score": 0.95,
                            "weighted": 0.38,
                            "description": f"Live GraphSense cluster resolution ({ent_label})",
                        },
                        "path_proximity": {
                            "weight": 0.30,
                            "score": 1.0 if hop_count <= 2 else 0.8,
                            "weighted": 0.30 if hop_count <= 2 else 0.24,
                            "description": f"Hop count {hop_count} proximity score",
                        },
                        "cluster_verification": {
                            "weight": 0.30,
                            "score": 0.90,
                            "weighted": 0.27,
                            "description": f"Cluster #{gs_match.get('cluster_id')}, Category: {primary_cat or 'N/A'}",
                        },
                    }

                    result = AttributionResult(
                        run_id=run_id,
                        matched_entity=ent_label,
                        rule_fired="LIVE_GRAPHSENSE_ENTITY_MATCH",
                        confidence=conf,
                        confidence_band=band,
                        score_breakdown={
                            "factors": factors,
                            "total_score": round(conf, 4),
                            "confidence_band": band,
                            "hop_count": hop_count,
                            "cluster_id": gs_match.get("cluster_id"),
                            "actor_id": gs_match.get("actor_id"),
                            "entity_category": primary_cat,
                            "categories": cats,
                        },
                        attribution_source="LIVE_GRAPHSENSE_API",
                        entity_category=primary_cat,
                        entity_categories=cats,
                    )
                    self._persist_attribution(result, db)
                    return result
            except Exception as ex:
                pass  # Graceful fallback to Tier (c) and (d)

        # ======================================================================
        # Tier (c): OFAC Sanctions Match (Phase 8D)
        # ======================================================================
        if db is not None and clean_candidate:
            sanction_row = (
                db.query(SanctionsList)
                .filter(
                    (SanctionsList.address == clean_candidate)
                    | (SanctionsList.address == clean_candidate.lower())
                )
                .first()
            )
            if sanction_row:
                ent_label = f"OFAC SDN MATCH: {sanction_row.entity_name}"
                result = AttributionResult(
                    run_id=run_id,
                    matched_entity=ent_label,
                    rule_fired="OFAC_SANCTIONS_MATCH",
                    confidence=1.0,
                    confidence_band="VERY_HIGH",
                    score_breakdown={
                        "rule": "OFAC_SANCTIONS_MATCH",
                        "sanction_program": sanction_row.program,
                        "source": sanction_row.source,
                        "entity_category": "sanction",
                        "total_score": 1.0,
                        "confidence_band": "VERY_HIGH",
                        "hop_count": hop_count,
                    },
                    attribution_source="OFAC_SDN_SANCTIONS_LIST",
                    entity_category="sanction",
                    entity_categories=["sanction"],
                )
                self._persist_attribution(result, db)
                return result

        # ======================================================================
        # Tier (d): CEX Sweep-Heuristic Match (Phase 4 / vasp_directory)
        # ======================================================================
        if not paths:
            # 0-hop Root address self-attribution check
            if matched_entity:
                result = AttributionResult(
                    run_id=run_id,
                    matched_entity=matched_entity,
                    rule_fired="ROOT_ADDRESS_IS_KNOWN_ENTITY",
                    confidence=1.0,
                    confidence_band="VERY_HIGH",
                    score_breakdown={
                        "factors": {
                            "root_entity_direct_match": 1.0,
                            "sweep_label_match": 1.0,
                            "path_proximity": 1.0,
                        },
                        "total_score": 1.0,
                        "reason": f"Root address belongs directly to verified entity {matched_entity} (0 hops required).",
                    },
                    attribution_source="ROOT_ADDRESS_IS_KNOWN_ENTITY",
                    entity_category="exchange",
                    entity_categories=["exchange"],
                )
                self._persist_attribution(result, db)
                return result

            # Empty trace without match
            result = AttributionResult(
                run_id=run_id,
                matched_entity="Insufficient Evidence",
                rule_fired="NO_PATH_DETECTED",
                confidence=0.0,
                confidence_band="INSUFFICIENT_EVIDENCE",
                score_breakdown={
                    "factors": {},
                    "total_score": 0.0,
                    "reason": "Trace path is empty.",
                },
                attribution_source="NO_PATH_DETECTED",
            )
            self._persist_attribution(result, db)
            return result

        # Multi-hop trace path evaluation
        final_hop = paths[-1]

        # 1. Sweep / Label Match Factor (Weight 0.35)
        sweep_score = 1.0 if matched_entity is not None else 0.0

        # 2. Path Proximity Factor (Weight 0.20)
        if hop_count <= 2:
            proximity_score = 1.0
        elif hop_count == 3:
            proximity_score = 0.85
        elif hop_count <= 5:
            proximity_score = 0.60
        elif hop_count <= 7:
            proximity_score = 0.40
        else:
            proximity_score = 0.15

        # 3. Deposit-Pattern Similarity (Weight 0.15)
        initial_val = float(paths[0].value) if paths[0].value else 1.0
        final_val = float(final_hop.value) if final_hop.value else 0.0
        val_retention = final_val / initial_val if initial_val > 0 else 0.0

        if matched_entity and val_retention >= 0.85:
            deposit_pattern_score = 1.0
        elif matched_entity and val_retention >= 0.50:
            deposit_pattern_score = 0.75
        elif matched_entity:
            deposit_pattern_score = 0.50
        else:
            deposit_pattern_score = 0.10

        # 4. Temporal Correlation (Weight 0.15)
        if matched_entity and hop_count <= 3:
            temporal_score = 0.95
        elif matched_entity and hop_count <= 5:
            temporal_score = 0.70
        else:
            temporal_score = 0.15

        # 5. Co-spend Cluster (Weight 0.10)
        if matched_entity and hop_count <= 3:
            co_spend_score = 0.90
        elif matched_entity:
            co_spend_score = 0.65
        else:
            co_spend_score = 0.05

        # 6. Behavioral Heuristic (Weight 0.05)
        if matched_entity:
            behavioral_score = 0.80
        else:
            behavioral_score = 0.10

        factors = {
            "sweep_label_match": {
                "weight": WEIGHTS["sweep_label_match"],
                "score": sweep_score,
                "weighted": sweep_score * WEIGHTS["sweep_label_match"],
                "description": "Direct sweep to verified exchange hot wallet" if sweep_score == 1.0 else "No verified hot wallet match",
            },
            "path_proximity": {
                "weight": WEIGHTS["path_proximity"],
                "score": proximity_score,
                "weighted": proximity_score * WEIGHTS["path_proximity"],
                "description": f"Hop count {hop_count} proximity score",
            },
            "deposit_pattern_similarity": {
                "weight": WEIGHTS["deposit_pattern_similarity"],
                "score": deposit_pattern_score,
                "weighted": deposit_pattern_score * WEIGHTS["deposit_pattern_similarity"],
                "description": f"Value retention: {val_retention:.1%}",
            },
            "temporal_correlation": {
                "weight": WEIGHTS["temporal_correlation"],
                "score": temporal_score,
                "weighted": temporal_score * WEIGHTS["temporal_correlation"],
                "description": "Rapid sweep timing" if temporal_score > 0.5 else "Extended latency / dilution",
            },
            "co_spend_cluster": {
                "weight": WEIGHTS["co_spend_cluster"],
                "score": co_spend_score,
                "weighted": co_spend_score * WEIGHTS["co_spend_cluster"],
                "description": "Exchange consolidation cluster detected" if co_spend_score > 0.5 else "No cluster match",
            },
            "behavioral": {
                "weight": WEIGHTS["behavioral"],
                "score": behavioral_score,
                "weighted": behavioral_score * WEIGHTS["behavioral"],
                "description": "Standard deposit routing behavior" if behavioral_score > 0.5 else "Unrecognized behavior",
            },
        }

        total_score = sum(f["weighted"] for f in factors.values())
        band = get_confidence_band(total_score)

        if sweep_score == 1.0 and hop_count <= 2:
            rule_fired = "SWEEP_TO_HOT_WALLET_DIRECT"
            attr_source = "CEX_SWEEP_HEURISTIC"
        elif sweep_score == 1.0:
            rule_fired = "VASP_HOT_WALLET_CONVERGENCE"
            attr_source = "CEX_SWEEP_HEURISTIC"
        elif band == "INSUFFICIENT_EVIDENCE":
            rule_fired = "UNVERIFIED_CLUSTER_INSUFFICIENT_EVIDENCE"
            attr_source = "UNVERIFIED_CLUSTER"
        else:
            rule_fired = "HEURISTIC_CLUSTER_MATCH"
            attr_source = "CEX_SWEEP_HEURISTIC"

        entity_name = matched_entity if matched_entity else "Insufficient Evidence"

        result = AttributionResult(
            run_id=run_id,
            matched_entity=entity_name,
            rule_fired=rule_fired,
            confidence=total_score,
            confidence_band=band,
            score_breakdown={
                "factors": factors,
                "total_score": round(total_score, 4),
                "confidence_band": band,
                "hop_count": hop_count,
                "matched_hot_wallet": matched_hot_wallet,
            },
            attribution_source=attr_source,
            entity_category="exchange" if matched_entity else None,
            entity_categories=["exchange"] if matched_entity else [],
        )

        self._persist_attribution(result, db)
        return result

    def _persist_attribution(self, result: AttributionResult, db: Optional[Session] = None):
        """Persist attribution entry to database."""
        if db is None:
            return

        attribution_row = Attribution(
            id=generate_uuid(),
            run_id=result.run_id,
            matched_entity=result.matched_entity,
            rule_fired=result.rule_fired,
            confidence=round(result.confidence, 4),
            entity_category=result.entity_category,
            score_breakdown=result.score_breakdown,
        )
        db.add(attribution_row)
        db.commit()
