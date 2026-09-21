"""Composite Risk Score Engine (0-100).
Combines VASP attribution confidence, money laundering typologies, and taint contamination.
Produces an explainable per-factor breakdown for investigating officers.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import List, Dict, Any, Optional
from app.services.attribution import AttributionResult
from app.services.typology import TypologyHit
from app.services.taint_engine import TaintResult


class RiskAssessment:
    def __init__(
        self,
        composite_score: int,
        risk_level: str,
        factors: Dict[str, Any],
        explanation: str,
    ):
        self.composite_score = composite_score  # 0 to 100
        self.risk_level = risk_level  # CRITICAL, HIGH, MEDIUM, LOW
        self.factors = factors
        self.explanation = explanation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite_score": self.composite_score,
            "risk_level": self.risk_level,
            "factors": self.factors,
            "explanation": self.explanation,
        }


class RiskEngine:
    """Computes explainable composite 0-100 risk score."""

    def compute_risk(
        self,
        attribution: AttributionResult,
        typologies: List[TypologyHit],
        taint: TaintResult,
    ) -> RiskAssessment:
        """Combine confidence, typology severity, and taint ratio into explainable composite score."""
        # 1. Attribution Confidence Contribution (Weight: 40%)
        attr_confidence_score = float(attribution.confidence) * 100.0
        attr_contribution = attr_confidence_score * 0.40

        # Extract entity category (Phase 8E)
        entity_cat = getattr(attribution, "entity_category", None)
        if not entity_cat and isinstance(attribution.score_breakdown, dict):
            entity_cat = attribution.score_breakdown.get("entity_category")
        norm_cat = (entity_cat or "").lower()

        # 2. Typology Severity Contribution (Weight: 40%)
        # Sum typology scores based on laundering severity
        typology_severity_map = {
            "MIXER": 45.0,
            "ILLICIT_SERVICE": 45.0,
            "CYBERCRIME_ACTOR": 45.0,
            "SANCTIONED_ENTITY": 50.0,
            "FAN_OUT": 25.0,
            "PEELING_CHAIN": 20.0,
            "LAYERING": 15.0,
            "DEFI_INTERACTION": 15.0,
        }
        raw_typo_score = sum(typology_severity_map.get(t.typology, 10.0) for t in typologies)
        normalized_typo_score = min(100.0, raw_typo_score)
        typo_contribution = normalized_typo_score * 0.40

        # 3. Taint Contamination Contribution (Weight: 20%)
        taint_score = float(taint.final_taint_percentage)
        taint_contribution = taint_score * 0.20

        # Composite score (0 - 100)
        composite = round(attr_contribution + typo_contribution + taint_contribution)

        # Severe risk category floor for mixers, darknet, ransomware, and sanctions
        if norm_cat in ("mixing_service", "mixer", "dark_web", "darknet_market", "drugs", "weapons", "ransomware", "phishing", "hacking", "sanction"):
            composite = max(85, composite)

        composite = max(0, min(100, composite))

        # Risk Level Banding
        if composite >= 80:
            risk_level = "CRITICAL"
        elif composite >= 60:
            risk_level = "HIGH"
        elif composite >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Construct narrative explanation
        typo_names = [t.typology for t in typologies]
        typo_str = ", ".join(typo_names) if typo_names else "no typologies detected"

        if attribution.matched_entity and attribution.matched_entity != "Insufficient Evidence":
            cat_str = f" ({norm_cat})" if norm_cat else ""
            dest_str = f"verified off-ramp to {attribution.matched_entity}{cat_str} ({round(attr_confidence_score)}% confidence)"
        else:
            dest_str = "unverified off-ramp / insufficient evidence"

        explanation = (
            f"Risk score of {composite}/100 ({risk_level}). "
            f"Evaluated against: {dest_str}, "
            f"laundering typologies [{typo_str}], and {round(taint_score, 1)}% FIFO taint contamination."
        )

        factors = {
            "attribution_factor": {
                "weight": 0.40,
                "score": round(attr_confidence_score, 1),
                "contribution": round(attr_contribution, 1),
                "matched_entity": attribution.matched_entity,
                "entity_category": entity_cat,
                "confidence_band": attribution.confidence_band,
            },
            "typology_factor": {
                "weight": 0.40,
                "score": round(normalized_typo_score, 1),
                "contribution": round(typo_contribution, 1),
                "detected_typologies": typo_names,
                "count": len(typologies),
            },
            "taint_factor": {
                "weight": 0.20,
                "score": round(taint_score, 1),
                "contribution": round(taint_contribution, 1),
                "taint_percentage": round(taint.final_taint_percentage, 1),
                "tainted_value": round(taint.final_tainted_value, 4),
            },
        }

        return RiskAssessment(
            composite_score=composite,
            risk_level=risk_level,
            factors=factors,
            explanation=explanation,
        )
