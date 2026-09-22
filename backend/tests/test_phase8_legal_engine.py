"""Unit and integration test suite for Phase 8 Legal Mapping Engine.
Validates BNS, IPC, IT Act, and PMLA statutory mapping rules, date switch boundaries,
on-chain signal derivation (including cycle detection), YAML validation failure,
and mandatory disclaimers.
Reference: Phase 8 — Legal mapping engine, Ministry of Home Affairs / I4C.
"""

import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.legal.engine import LegalRulesEngine, load_rules, MANDATORY_DISCLAIMER, TRANSITION_DATE
from app.database import SessionLocal
from app.models import Profile, Case, WalletSubmission, AnalysisRun, TracePath, TypologyDetected, generate_uuid, utc_now
from app.security import create_access_token, hash_password


client = TestClient(app)


# ==============================================================================
# 1. YAML Loader & Strict Schema Validation Tests
# ==============================================================================

def test_yaml_loader_and_schema_validation():
    """Verify that rules.yaml loads correctly and matches the closed provision table."""
    rules = load_rules()

    assert "rules_version" in rules
    assert "disclaimer" in rules
    assert MANDATORY_DISCLAIMER in rules["disclaimer"]
    assert "provisions" in rules
    assert "typologies" in rules

    provisions = rules["provisions"]
    # Exactly 13 provisions as strictly defined
    assert len(provisions) == 13

    # Check verified flags strictly
    verified_true = {"bns_318_4", "bns_316", "bns_61", "bns_303"}
    for p_id, p_data in provisions.items():
        assert "act" in p_data
        assert "section" in p_data
        assert "title" in p_data
        assert "ipc_equivalent" in p_data
        assert "verified" in p_data
        assert p_data["verify_at"] == "https://indiacode.nic.in"

        if p_id in verified_true:
            assert p_data["verified"] is True, f"Expected {p_id} to be verified: true"
        else:
            assert p_data["verified"] is False, f"Expected {p_id} to be verified: false"

    # All 7 typologies present
    expected_typos = {
        "investment_scam",
        "phishing_impersonation",
        "hack_theft",
        "ransomware_extortion",
        "sextortion",
        "insider_misappropriation",
        "layering_laundering",
    }
    assert set(rules["typologies"].keys()) == expected_typos


def test_yaml_validation_failure_on_malformed_syntax():
    """Verify loader raises ValueError on malformed YAML syntax."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write("rules_version: 1.0.0\nprovisions: [unclosed list\n")
        temp_path = tf.name

    try:
        with pytest.raises(ValueError, match="Malformed YAML"):
            load_rules(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_yaml_validation_failure_on_missing_top_level_keys():
    """Verify loader raises ValueError when required top-level keys are absent."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write("rules_version: 1.0.0\nprovisions: {}\n")
        temp_path = tf.name

    try:
        with pytest.raises(ValueError, match="missing required top-level key"):
            load_rules(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_yaml_validation_failure_on_invalid_provision_data():
    """Verify loader raises ValueError when provision fields are incomplete or invalid."""
    invalid_content = """
rules_version: "1.0.0"
disclaimer: "test"
provisions:
  bad_prov:
    act: "BNS"
    section: "999"
    # missing title, ipc_equivalent, verified, verify_at
typologies:
  test_typo:
    provisions: ["bad_prov"]
    checklist: []
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(invalid_content)
        temp_path = tf.name

    try:
        with pytest.raises(ValueError, match="missing required field"):
            load_rules(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_yaml_validation_failure_on_unknown_provision_reference():
    """Verify loader raises ValueError when a typology references a nonexistent provision."""
    invalid_content = """
rules_version: "1.0.0"
disclaimer: "test"
provisions:
  p1:
    act: "BNS"
    section: "1"
    title: "T"
    ipc_equivalent: null
    verified: false
    verify_at: "https://indiacode.nic.in"
typologies:
  t1:
    provisions: ["p_does_not_exist"]
    checklist: []
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(invalid_content)
        temp_path = tf.name

    try:
        with pytest.raises(ValueError, match="references unknown provision"):
            load_rules(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_yaml_validation_failure_on_invalid_checklist_source_or_signal():
    """Verify loader raises ValueError when checklist item has invalid source or signal."""
    invalid_content = """
rules_version: "1.0.0"
disclaimer: "test"
provisions:
  p1:
    act: "BNS"
    section: "1"
    title: "T"
    ipc_equivalent: null
    verified: false
    verify_at: "https://indiacode.nic.in"
typologies:
  t1:
    provisions: ["p1"]
    checklist:
      - ingredient: "Something"
        source: "invalid_source_here"
        signal: null
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(invalid_content)
        temp_path = tf.name

    try:
        with pytest.raises(ValueError, match="Invalid source"):
            load_rules(temp_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


# ==============================================================================
# 2. Date Switch Boundary Tests (2024-07-01)
# ==============================================================================

def test_date_switch_before_2024_07_01():
    """Offence date prior to 1 July 2024 must return IPC equivalents as primary."""
    engine = LegalRulesEngine()

    for pre_date in ["2024-06-30", "2024-01-01", "2023-11-20"]:
        res = engine.suggest_provisions(typology="investment_scam", offence_date=pre_date)
        assert res["scheme"] == "IPC"
        assert "Indian Penal Code (IPC) applies" in res["scheme_note"]
        assert res["offence_date"] == pre_date

        # BNS 318(4) corresponds to IPC 420; under IPC scheme, IPC 420 must be primary
        cheating_prov = next(p for p in res["provisions"] if p["id"] == "bns_318_4")
        assert cheating_prov["primary_display"].startswith("IPC 420")
        assert "BNS 318(4)" in cheating_prov["secondary_display"]


def test_date_switch_on_or_after_2024_07_01():
    """Offence date on or after 1 July 2024 must return BNS as primary."""
    engine = LegalRulesEngine()

    for post_date in ["2024-07-01", "2024-07-02", "2025-01-15", "2026-09-22"]:
        res = engine.suggest_provisions(typology="investment_scam", offence_date=post_date)
        assert res["scheme"] == "BNS"
        assert "Bharatiya Nyaya Sanhita (BNS) applies" in res["scheme_note"]
        assert res["offence_date"] == post_date

        cheating_prov = next(p for p in res["provisions"] if p["id"] == "bns_318_4")
        assert cheating_prov["primary_display"].startswith("BNS 318(4)")
        assert "IPC 420" in cheating_prov["secondary_display"]


def test_date_switch_missing_date_returns_both():
    """Missing offence date must return both schemes and indicate date is required."""
    engine = LegalRulesEngine()

    for missing_input in [None, "", "   "]:
        res = engine.suggest_provisions(typology="investment_scam", offence_date=missing_input)
        assert res["scheme"] == "BOTH"
        assert "offence date determines whether IPC" in res["scheme_note"]
        assert res["offence_date"] is None

        cheating_prov = next(p for p in res["provisions"] if p["id"] == "bns_318_4")
        assert "BNS 318(4)" in cheating_prov["primary_display"]
        assert "IPC 420" in cheating_prov["primary_display"]


# ==============================================================================
# 3. Ingredients Checklist & On-Chain Signal Derivation Tests
# ==============================================================================

def test_checklist_cycle_detected_signal_derivation():
    """Verify cycle_detected signal evaluates to 'present' when trace has a cycle."""
    engine = LegalRulesEngine()

    # Case A: Trace result has explicit cycles detected
    trace_with_cycle = {
        "paths": [
            {"from": "0xAddrA", "to": "0xAddrB", "value": 5.0},
            {"from": "0xAddrB", "to": "0xAddrC", "value": 5.0},
            {"from": "0xAddrC", "to": "0xAddrA", "value": 5.0},
        ],
        "cycles": [{"nodes": ["0xAddrA", "0xAddrB", "0xAddrC", "0xAddrA"]}],
        "typologies": [{"typology": "LAYERING"}],
    }

    res = engine.suggest_provisions(
        typology="layering_laundering",
        offence_date="2024-08-01",
        trace_result=trace_with_cycle,
    )

    cycle_item = next(
        item for item in res["ingredients_checklist"]
        if item.get("signal") == "cycle_detected"
    )
    assert cycle_item["status"] == "present"
    assert "detected in transaction graph" in cycle_item["details"]

    # Case B: Trace result has NO cycle
    trace_no_cycle = {
        "paths": [
            {"from": "0xAddrA", "to": "0xAddrB", "value": 5.0},
            {"from": "0xAddrB", "to": "0xAddrC", "value": 5.0},
        ],
        "cycles": [],
        "typologies": [],
    }

    res_no_cycle = engine.suggest_provisions(
        typology="layering_laundering",
        offence_date="2024-08-01",
        trace_result=trace_no_cycle,
    )

    cycle_item_no = next(
        item for item in res_no_cycle["ingredients_checklist"]
        if item.get("signal") == "cycle_detected"
    )
    assert cycle_item_no["status"] == "missing"
    assert "No circular flow loops" in cycle_item_no["details"]


def test_checklist_signals_multi_hop_and_mixer():
    """Verify multi_hop_layering, mixer_exposure, exchange_endpoint, peel_chain signals."""
    engine = LegalRulesEngine()

    trace_complex = {
        "paths": [
            {"from": "0xA", "to": "0xB", "heuristicBadge": "MIXER"},
            {"from": "0xB", "to": "0xC"},
            {"from": "0xC", "to": "0xD"},
        ],
        "typologies": [{"typology": "MIXER"}, {"typology": "PEELING_CHAIN"}],
        "reached_vasp": True,
        "vasp_name": "CoinDCX",
    }

    signals = engine.evaluate_signals(trace_complex)
    assert signals["multi_hop_layering"][0] is True
    assert signals["mixer_exposure"][0] is True
    assert signals["exchange_endpoint"][0] is True
    assert signals["peel_chain"][0] is True
    assert signals["sanctioned_exposure"][0] is False


def test_checklist_officer_and_complaint_sources():
    """Checklist items with source 'officer' require input; 'complaint' checks case reporting."""
    engine = LegalRulesEngine()

    # With complaint info
    res = engine.suggest_provisions(
        typology="investment_scam",
        case_data={"victim_utr": "UTR12345", "amount_inr": 50000.0},
    )

    complaint_items = [i for i in res["ingredients_checklist"] if i["source"] == "complaint"]
    assert len(complaint_items) > 0
    for ci in complaint_items:
        assert ci["status"] == "present"

    officer_items = [i for i in res["ingredients_checklist"] if i["source"] == "officer"]
    assert len(officer_items) > 0
    for oi in officer_items:
        assert oi["status"] == "needs_officer_input"


# ==============================================================================
# 4. Mandatory Disclaimers and Badges Tests
# ==============================================================================

def test_disclaimers_and_badges_present_in_all_typologies():
    """Every response must carry rules_version, disclaimer, and strictly Cross-checked/Unverified badges."""
    engine = LegalRulesEngine()

    for typo_key in engine.rules["typologies"].keys():
        res = engine.suggest_provisions(typology=typo_key, offence_date="2024-07-15")

        assert "rules_version" in res
        assert "disclaimer" in res
        assert MANDATORY_DISCLAIMER in res["disclaimer"]

        for prov in res["provisions"]:
            assert prov["badge"] in ("Cross-checked", "Unverified")
            assert prov["badge"] != "Confirmed"
            assert prov["badge"] != "Officially Confirmed"
            assert prov["verify_at"] == "https://indiacode.nic.in"


# ==============================================================================
# 5. API Endpoint Tests (POST /api/v1/cases/{id}/legal-suggestions)
# ==============================================================================

@pytest.fixture
def auth_headers_investigator():
    db = SessionLocal()
    officer = db.query(Profile).filter(Profile.role == "INVESTIGATOR").first()
    if not officer:
        officer = Profile(
            id=generate_uuid(),
            email=f"test_inv_{generate_uuid()[:6]}@sentinel.gov.in",
            password_hash=hash_password("Pass123!"),
            full_name="SI Test Investigator",
            badge_no="TEST-001",
            role="INVESTIGATOR",
        )
        db.add(officer)
        db.commit()
        db.refresh(officer)
    db.close()
    token = create_access_token(officer_id=officer.id, email=officer.email, role=officer.role)
    return {"Authorization": f"Bearer {token}"}, officer



@pytest.fixture
def test_case_with_trace(auth_headers_investigator):
    _, officer = auth_headers_investigator
    db = SessionLocal()
    case = Case(
        case_id=generate_uuid(),
        ncrp_ref="NCRP/2026/TEST-LEGAL-01",
        victim_utr="UTR-999888777",
        victim_utr_timestamp=utc_now(),
        amount_inr=150000.0,
        assigned_officer_id=officer.id,
        status="OPEN",
    )
    db.add(case)
    db.flush()

    sub = WalletSubmission(
        submission_id=generate_uuid(),
        case_id=case.case_id,
        chain="ETH",
        address="0x1111111111111111111111111111111111111111",
    )
    db.add(sub)
    db.flush()

    run = AnalysisRun(
        run_id=generate_uuid(),
        submission_id=sub.submission_id,
        status="COMPLETED",
        completed_at=utc_now(),
    )
    db.add(run)
    db.flush()

    # Add trace paths forming a cycle
    p1 = TracePath(run_id=run.run_id, hop_index=1, from_addr="0xAlpha", to_addr="0xBeta", chain="ETH", value=1.0)
    p2 = TracePath(run_id=run.run_id, hop_index=2, from_addr="0xBeta", to_addr="0xGamma", chain="ETH", value=1.0)
    p3 = TracePath(run_id=run.run_id, hop_index=3, from_addr="0xGamma", to_addr="0xAlpha", chain="ETH", value=1.0)
    db.add_all([p1, p2, p3])

    t1 = TypologyDetected(run_id=run.run_id, typology="LAYERING", hop_start=1, hop_end=3)
    db.add(t1)

    db.commit()
    db.refresh(case)
    case_id = case.case_id
    db.close()
    return case_id


def test_api_legal_suggestions_post_v1(auth_headers_investigator, test_case_with_trace):
    """Test POST /api/v1/cases/{id}/legal-suggestions with case trace result."""
    headers, _ = auth_headers_investigator
    case_id = test_case_with_trace

    payload = {
        "typology": "layering_laundering",
        "offence_date": "2024-05-15",
    }

    # Test v1 endpoint
    resp = client.post(f"/api/v1/cases/{case_id}/legal-suggestions", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["rules_version"] == "1.0.0"
    assert MANDATORY_DISCLAIMER in data["disclaimer"]
    assert data["scheme"] == "IPC"
    assert data["offence_date"] == "2024-05-15"
    assert len(data["provisions"]) > 0

    # Stored trace path had 0xAlpha -> 0xBeta -> 0xGamma -> 0xAlpha (cycle detected)
    cycle_check = next(
        (item for item in data["ingredients_checklist"] if item.get("signal") == "cycle_detected"),
        None,
    )
    assert cycle_check is not None
    assert cycle_check["status"] == "present"

    # Also test /api/cases/{case_id}/legal-suggestions
    resp2 = client.post(f"/api/cases/{case_id}/legal-suggestions", json=payload, headers=headers)
    assert resp2.status_code == 200


def test_api_legal_suggestions_unknown_typology(auth_headers_investigator, test_case_with_trace):
    """Test that invalid typology returns HTTP 400."""
    headers, _ = auth_headers_investigator
    case_id = test_case_with_trace

    payload = {"typology": "non_existent_typology_xyz"}
    resp = client.post(f"/api/v1/cases/{case_id}/legal-suggestions", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "Unknown typology" in resp.json()["detail"]


def test_api_legal_suggestions_case_not_found(auth_headers_investigator):
    """Test that non-existent case returns HTTP 404."""
    headers, _ = auth_headers_investigator
    payload = {"typology": "investment_scam"}
    resp = client.post("/api/v1/cases/00000000-0000-0000-0000-000000000000/legal-suggestions", json=payload, headers=headers)
    assert resp.status_code == 404
