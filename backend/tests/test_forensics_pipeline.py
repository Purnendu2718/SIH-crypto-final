"""Pytest suite for Phase 4: Attribution, Risk, Typology, and Taint Engines.
Verifies end-to-end forensic execution across all 4 scenarios.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import pytest
from app.database import SessionLocal, init_db
from app.services import run_full_forensic_pipeline


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_scenario_1_high_confidence_direct_sweep(db):
    """Scenario 1: Direct 2-hop sweep to CoinDCX produces HIGH/VERY_HIGH confidence and explainable risk."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    res = run_full_forensic_pipeline(start_address=suspect_addr, chain="ETH", db=db)

    # 1. Trace Check
    assert res["status"] == "COMPLETED"
    assert res["trace"]["total_hops"] == 2

    # 2. Attribution Check
    attr = res["attribution"]
    assert attr["matched_entity"] == "CoinDCX"
    assert attr["rule_fired"] == "SWEEP_TO_HOT_WALLET_DIRECT"
    assert attr["confidence"] >= 0.65, f"Expected HIGH/VERY_HIGH confidence, got {attr['confidence']}"
    assert attr["confidence_band"] in ["HIGH", "VERY_HIGH"]

    # Check score breakdown
    factors = attr["score_breakdown"]["factors"]
    assert factors["sweep_label_match"]["score"] == 1.0
    assert factors["path_proximity"]["score"] == 1.0

    # 3. Taint Check
    taint = res["taint"]
    assert taint["final_taint_percentage"] == 100.0

    # 4. Risk Check
    risk = res["risk"]
    assert "composite_score" in risk
    assert risk["composite_score"] >= 50
    assert "attribution_factor" in risk["factors"]
    assert "typology_factor" in risk["factors"]
    assert "taint_factor" in risk["factors"]
    assert len(risk["explanation"]) > 0


def test_scenario_2_fanout_and_mixer_detection(db):
    """Scenario 2: Detects FAN_OUT and MIXER typologies converging at WazirX."""
    suspect_addr = "0x3a9F784260D672b15Fa0e20f18837138096c7B22"
    res = run_full_forensic_pipeline(start_address=suspect_addr, chain="ETH", db=db)

    assert res["status"] == "COMPLETED"
    assert res["attribution"]["matched_entity"] == "WazirX"

    # Typologies Check
    typo_names = [t["typology"] for t in res["typologies"]]
    assert "FAN_OUT" in typo_names, f"Expected FAN_OUT in {typo_names}"
    assert "MIXER" in typo_names, f"Expected MIXER in {typo_names}"

    # Risk score should reflect high severity due to mixer
    assert res["risk"]["factors"]["typology_factor"]["score"] >= 50


def test_scenario_3_crosschain_layering_detection(db):
    """Scenario 3: Detects cross-chain bridge LAYERING landing at ZebPay."""
    suspect_addr = "0x892a0194856cD192801F6281983017A8128919a0"
    res = run_full_forensic_pipeline(start_address=suspect_addr, chain="ETH", db=db)

    assert res["status"] == "COMPLETED"
    assert res["attribution"]["matched_entity"] == "ZebPay"

    # Typologies Check
    typo_names = [t["typology"] for t in res["typologies"]]
    assert "LAYERING" in typo_names


def test_scenario_4_never_exceeds_medium_confidence(db):
    """Scenario 4: Long 8-hop peeling chain terminating at an unverified cluster.
    CRITICAL REQUIREMENT: Must NEVER produce a confidence above MEDIUM.
    """
    suspect_addr = "0x992dE819385610293751a09281754910284759A1"
    res = run_full_forensic_pipeline(start_address=suspect_addr, chain="ETH", db=db)

    assert res["status"] == "NO_CONFIDENT_OFF_RAMP"

    attr = res["attribution"]
    # Explicit check: Never above MEDIUM
    assert attr["confidence"] < 0.40, f"Scenario 4 confidence ({attr['confidence']}) exceeded threshold!"
    assert attr["confidence_band"] == "INSUFFICIENT_EVIDENCE"
    assert attr["matched_entity"] == "Insufficient Evidence"

    # Typologies Check
    typo_names = [t["typology"] for t in res["typologies"]]
    assert "PEELING_CHAIN" in typo_names

    # Risk Assessment
    risk = res["risk"]
    assert risk["factors"]["attribution_factor"]["confidence_band"] == "INSUFFICIENT_EVIDENCE"


def test_empty_trace_returns_insufficient_evidence(db):
    """Confirm an empty / unresolvable address safely returns INSUFFICIENT_EVIDENCE."""
    res = run_full_forensic_pipeline(start_address="0x0000000000000000000000000000000000000000", chain="ETH", db=db)
    assert res["attribution"]["confidence_band"] == "INSUFFICIENT_EVIDENCE"
    assert res["attribution"]["confidence"] == 0.0
    assert res["status"] == "NO_CONFIDENT_OFF_RAMP"
