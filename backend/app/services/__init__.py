"""Forensics and analysis services package exports and unified pipeline coordinator.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8C Hotfixes.
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models import AnalysisRun, utc_now, generate_uuid
from app.services.trace_engine import TraceEngine, TraceResult, ForensicStatus
from app.services.attribution import AttributionEngine, AttributionResult
from app.services.typology import TypologyEngine, TypologyHit
from app.services.taint_engine import TaintEngine, TaintResult
from app.services.risk_engine import RiskEngine, RiskAssessment
from app.services.address_validator import validate_and_detect_chain
from app.services.adapters.fixture_adapter import FixtureAdapter


def run_full_forensic_pipeline(
    start_address: str,
    chain: str = "ETH",
    run_id: Optional[str] = None,
    stolen_principal: Optional[float] = None,
    max_hops: int = 15,
    dust_threshold: float = 0.001,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Execute complete end-to-end forensics:
    1. Cryptographic Address Validation & Chain Detection
    2. Root-Address Self-Attribution Check (0-hop short circuit)
    3. Bounded BFS Multi-Hop Trace
    4. Explainable Attribution Scoring
    5. Laundering Typology Detection
    6. FIFO Contamination Accounting
    7. Composite Risk Assessment.
    """
    active_run_id = run_id or generate_uuid()

    # Step 1: Strict Cryptographic Address Checksum Validation
    is_valid, detected_chain_or_err, validation_detail = validate_and_detect_chain(start_address)

    # Offline-first fallback: recognize seeded demo scenarios
    if not is_valid:
        try:
            fa = FixtureAdapter()
            if fa.get_scenario_by_address(start_address):
                is_valid = True
                detected_chain_or_err = chain or "ETH"
                validation_detail = f"FIXTURE {detected_chain_or_err}"
        except Exception:
            pass

    if not is_valid:
        failed_status = ForensicStatus("ANALYSIS_FAILED_INVALID_ADDRESS")
        if db is not None:
            db_run = db.query(AnalysisRun).filter(AnalysisRun.run_id == active_run_id).first()
            if db_run:
                db_run.status = str(failed_status)
                db_run.completed_at = utc_now()
                db.commit()

        return {
            "run_id": active_run_id,
            "status": failed_status,
            "error": validation_detail,
            "error_code": "UNRECOGNIZED_ADDRESS_FORMAT",
            "address": start_address,
            "chain": chain,
            "is_root_entity": False,
            "attribution_source": "INVALID_ADDRESS_FORMAT",
            "trace": {
                "run_id": active_run_id,
                "status": str(failed_status),
                "total_hops": 0,
                "matched_entity": None,
                "matched_hot_wallet": None,
                "visited_addresses": [start_address],
                "paths": [],
            },
            "attribution": {
                "run_id": active_run_id,
                "matched_entity": "Invalid Address Format",
                "rule_fired": "UNRECOGNIZED_ADDRESS_FORMAT",
                "confidence": 0.0,
                "confidence_band": "INSUFFICIENT_EVIDENCE",
                "attribution_source": "INVALID_ADDRESS_FORMAT",
                "score_breakdown": {
                    "factors": {},
                    "total_score": 0.0,
                    "reason": validation_detail,
                },
            },
            "typologies": [],
            "taint": {"taint_ratio": 0.0, "tainted_amount": 0.0, "contamination_percentage": 0.0},
            "risk": {
                "composite_score": 0.0,
                "risk_level": "LOW",
                "factors": {},
                "explanation": "Analysis failed due to invalid address checksum format.",
            },
        }

    # Use detected chain if caller used default ETH but address is strictly BTC or TRON
    active_chain = detected_chain_or_err if detected_chain_or_err in ("BTC", "TRON") else chain

    # Step 2: Multi-Hop Trace Engine (with internal Root-Address Self-Attribution check)
    try:
        trace_eng = TraceEngine(max_hops=max_hops, dust_threshold=dust_threshold)
        trace_res: TraceResult = trace_eng.execute_trace(
            start_address=start_address,
            initial_chain=active_chain,
            run_id=active_run_id,
            db=db,
        )
    except Exception as e:
        # Live provider error / timeout / adapter failure
        adapter_err_status = ForensicStatus("ANALYSIS_FAILED_ADAPTER_ERROR")
        if db is not None:
            db_run = db.query(AnalysisRun).filter(AnalysisRun.run_id == active_run_id).first()
            if db_run:
                db_run.status = str(adapter_err_status)
                db_run.completed_at = utc_now()
                db.commit()

        return {
            "run_id": active_run_id,
            "status": adapter_err_status,
            "error": str(e),
            "error_code": "ADAPTER_EXECUTION_ERROR",
            "address": start_address,
            "chain": active_chain,
            "is_root_entity": False,
            "trace": {"run_id": active_run_id, "status": str(adapter_err_status), "paths": [], "total_hops": 0},
            "attribution": {"matched_entity": "Error", "rule_fired": "ADAPTER_ERROR", "confidence": 0.0},
            "typologies": [],
            "taint": {"taint_ratio": 0.0},
            "risk": {"composite_score": 0.0, "risk_level": "LOW"},
        }

    # Step 3: Attribution Engine
    attr_eng = AttributionEngine()
    attr_res: AttributionResult = attr_eng.compute_attribution(
        run_id=trace_res.run_id,
        paths=trace_res.paths,
        matched_entity=trace_res.matched_entity,
        matched_hot_wallet=trace_res.matched_hot_wallet,
        target_address=start_address,
        chain=active_chain,
        db=db,
    )

    # Step 4: Typology Engine (with entity category propagation)
    typo_eng = TypologyEngine()
    typo_hits = typo_eng.detect_typologies(
        run_id=trace_res.run_id,
        paths=trace_res.paths,
        attributed_category=getattr(attr_res, "entity_category", None),
        attributed_entity=attr_res.matched_entity,
        db=db,
    )

    # Step 5: Taint Engine (FIFO)
    taint_eng = TaintEngine()
    taint_res: TaintResult = taint_eng.compute_fifo_taint(
        paths=trace_res.paths,
        stolen_principal=stolen_principal,
    )

    # Step 6: Composite Risk Engine
    risk_eng = RiskEngine()
    risk_res: RiskAssessment = risk_eng.compute_risk(
        attribution=attr_res,
        typologies=typo_hits,
        taint=taint_res,
    )

    is_root_entity = (len(trace_res.paths) == 0 and attr_res.confidence > 0.0)

    return {
        "run_id": trace_res.run_id,
        "status": trace_res.status,
        "chain": active_chain,
        "address": start_address,
        "is_root_entity": is_root_entity,
        "attribution_source": getattr(attr_res, "attribution_source", None),
        "entity_category": getattr(attr_res, "entity_category", None),
        "trace": trace_res.to_dict(),
        "attribution": attr_res.to_dict(),
        "typologies": [t.to_dict() for t in typo_hits],
        "taint": taint_res.to_dict(),
        "risk": risk_res.to_dict(),
    }


__all__ = [
    "TraceEngine",
    "TraceResult",
    "ForensicStatus",
    "AttributionEngine",
    "AttributionResult",
    "TypologyEngine",
    "TypologyHit",
    "TaintEngine",
    "TaintResult",
    "RiskEngine",
    "RiskAssessment",
    "run_full_forensic_pipeline",
]
