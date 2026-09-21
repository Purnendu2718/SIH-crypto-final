"""Isolated tests for Phase 7 — India-Specific Innovation Layer.
Verifies:
1. UPI-UTR Correlator (matching heuristic, temporal & amount tolerance windows)
2. Golden Hour Watchlist (CRUD, outbound off-ramp movement detection, stubbed webhook alert)
3. VASP Directory Admin View (ADMIN RBAC enforcement, CRUD updates)
4. Police Intel Exchange (Hash-and-RBAC architecture, client-side SHA-256 digests, zero PII)
5. "Arjuna" AI Co-pilot (strict non-hallucination factual summary in English and Hindi)
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import hashlib
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Profile, Case, WalletSubmission, AnalysisRun, Attribution, generate_uuid, utc_now
from app.database import SessionLocal, init_db
from app.security import hash_password, create_access_token
from app.services.upi_correlator import UPICorrelator
from app.services.watchlist_service import poll_all_watchlist_entries, check_watchlist_entry
from app.services.arjuna_copilot import ArjunaCopilot
from app.fixtures.seed_fixtures import seed_vasp_directory

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Ensure database schema is initialized and Indian VASP directory is seeded."""
    init_db()
    seed_vasp_directory()
    yield


@pytest.fixture
def auth_tokens():
    """Seed test officer profiles and return bearer auth headers."""
    db = SessionLocal()
    try:
        # Investigator
        inv = db.query(Profile).filter(Profile.email == "test_inv_p7@sentinel.gov.in").first()
        if not inv:
            inv = Profile(
                id=generate_uuid(),
                email="test_inv_p7@sentinel.gov.in",
                password_hash=hash_password("Pass123!"),
                full_name="Inspector R. K. Singh",
                badge_no="DEL-9912",
                role="INVESTIGATOR",
                district="Cyber Cell New Delhi",
            )
            db.add(inv)

        # Admin
        adm = db.query(Profile).filter(Profile.email == "test_admin_p7@sentinel.gov.in").first()
        if not adm:
            adm = Profile(
                id=generate_uuid(),
                email="test_admin_p7@sentinel.gov.in",
                password_hash=hash_password("AdminPass123!"),
                full_name="Director S. K. Gupta",
                badge_no="HQ-ADMIN-01",
                role="ADMIN",
                district="I4C Coordination HQ",
            )
            db.add(adm)

        db.commit()
        db.refresh(inv)
        db.refresh(adm)

        inv_token = create_access_token(inv.id, inv.email, inv.role)
        adm_token = create_access_token(adm.id, adm.email, adm.role)

        return {
            "inv": {"Authorization": f"Bearer {inv_token}", "officer_id": inv.id},
            "adm": {"Authorization": f"Bearer {adm_token}", "officer_id": adm.id},
        }
    finally:
        db.close()


# ==============================================================================
# 1. UPI-UTR Correlator Tests
# ==============================================================================

def test_upi_utr_correlator_matches_within_tolerance():
    """Correlates victim UTR within 15 min delta and 0.0% amount discrepancy."""
    victim_utr = "UPI-429188092144"
    reported_inr = 1125000.0
    victim_ts = datetime.fromisoformat("2026-09-01T09:45:00+00:00")

    # Sample candidates (including the Scenario 1 deposit of 4.5 ETH / ₹11,25,000 INR at 10:00:00Z)
    candidates = [
        {
            "tx_hash": "0xaaa1110000000000000000000000000000000000000000000000000000000001",
            "chain": "ETH",
            "from_address": "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
            "to_address": "0x918F4dE1a980598711E81D3962b9a764d2627E51",
            "value": 4.5,
            "value_inr": 1125000.0,
            "timestamp": "2026-09-01T10:00:00Z",
        },
        {
            "tx_hash": "0xunrelated00000000000000000000000000000000000000000000000000000002",
            "chain": "ETH",
            "from_address": "0xOtherAddr",
            "to_address": "0xReceiver",
            "value": 0.1,
            "value_inr": 25000.0,
            "timestamp": "2026-09-01T09:50:00Z",
        }
    ]

    result = UPICorrelator.correlate(
        victim_utr=victim_utr,
        reported_amount_inr=reported_inr,
        utr_timestamp=victim_ts,
        transactions=candidates,
        time_tolerance_minutes=120.0,
        amount_tolerance_percent=5.0,
    )

    assert result.correlation_status == "CORRELATED_MATCH_FOUND"
    assert len(result.matched_candidates) == 1
    assert result.best_candidate is not None
    assert result.best_candidate.tx_hash == candidates[0]["tx_hash"]
    assert result.best_candidate.is_correlated is True
    assert result.best_candidate.time_diff_minutes == 15.0
    assert result.best_candidate.amount_diff_inr == 0.0
    assert result.best_candidate.correlation_score >= 0.85
    assert "matches reported UTR" in result.best_candidate.explanation


def test_upi_utr_correlator_rejects_outside_tolerance():
    """Rejects candidates whose timestamp or amount falls outside the configured tolerance window."""
    victim_utr = "UPI-778899001122"
    reported_inr = 500000.0
    # Victim transaction was at 09:00:00Z
    victim_ts = datetime.fromisoformat("2026-09-01T09:00:00+00:00")

    # Transaction is 10 hours later (600 mins > 60 min tolerance)
    out_of_window_txs = [
        {
            "tx_hash": "0xlatedeposit",
            "chain": "ETH",
            "from_address": "0xFrom",
            "to_address": "0xTo",
            "value": 2.0,
            "value_inr": 500000.0,
            "timestamp": "2026-09-01T19:00:00Z",
        }
    ]

    result = UPICorrelator.correlate(
        victim_utr=victim_utr,
        reported_amount_inr=reported_inr,
        utr_timestamp=victim_ts,
        transactions=out_of_window_txs,
        time_tolerance_minutes=60.0,
        amount_tolerance_percent=5.0,
    )

    assert result.correlation_status == "NO_CANDIDATE_WITHIN_TOLERANCE"
    assert len(result.matched_candidates) == 0
    assert result.best_candidate is None


def test_upi_utr_correlator_endpoint_integration(auth_tokens):
    """Test standalone UTR matching API endpoint."""
    headers = {"Authorization": auth_tokens["inv"]["Authorization"]}
    payload = {
        "victim_utr": "UPI-DEMO-998877",
        "amount_inr": 1125000.0,
        "utr_timestamp": "2026-09-01T09:50:00Z",
        "address": "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
        "chain": "ETH",
        "time_tolerance_minutes": 120.0,
        "amount_tolerance_percent": 5.0,
    }

    res = client.post("/api/correlator/match", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["correlation_status"] == "CORRELATED_MATCH_FOUND"
    assert data["best_candidate"] is not None


# ==============================================================================
# 2. Golden Hour Watchlist Tests
# ==============================================================================

def test_golden_hour_watchlist_crud_and_polling_alert(auth_tokens):
    """Test full Golden Hour monitoring flow: register address, trigger poll, verify off-ramp alert."""
    headers = {"Authorization": auth_tokens["inv"]["Authorization"]}

    # Create a test case to bind the watchlist entry to
    case_res = client.post(
        "/api/cases",
        json={"ncrp_ref": "NCRP/2026/WATCHLIST-TEST-01", "victim_utr": "UPI-WATCHLIST-01", "amount_inr": 1125000.0},
        headers=headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["case_id"]

    # In scenario 1: "0x918F4dE1a980598711E81D3962b9a764d2627E51" sends 4.498 ETH to CoinDCX hot wallet
    monitored_addr = "0x918F4dE1a980598711E81D3962b9a764d2627E51"

    # 1. Create watchlist entry
    create_res = client.post(
        "/api/watchlist",
        json={"address": monitored_addr, "chain": "ETH", "case_id": case_id, "alert_channel": "TELEGRAM"},
        headers=headers,
    )
    assert create_res.status_code == 201
    entry_id = create_res.json()["id"]
    assert create_res.json()["status"] == "ACTIVE"

    # 2. List watchlist entries
    list_res = client.get(f"/api/watchlist?case_id={case_id}", headers=headers)
    assert list_res.status_code == 200
    assert any(e["id"] == entry_id for e in list_res.json())

    # 3. Trigger manual poll
    poll_res = client.post("/api/watchlist/poll-now", headers=headers)
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["total_checked"] >= 1
    assert poll_data["alerts_fired"] >= 1

    # Verify entry status was updated to TRIGGERED
    get_res = client.get(f"/api/watchlist/{entry_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "TRIGGERED"
    assert get_res.json()["last_alert_at"] is not None

    # 4. Clean up / Delete entry
    del_res = client.delete(f"/api/watchlist/{entry_id}", headers=headers)
    assert del_res.status_code == 200


# ==============================================================================
# 3. VASP Directory Admin Tests (RBAC & CRUD)
# ==============================================================================

def test_vasp_directory_admin_crud_and_rbac_enforcement(auth_tokens):
    """Verifies that INVESTIGATOR is denied admin mutations, and ADMIN can curate entries."""
    inv_headers = {"Authorization": auth_tokens["inv"]["Authorization"]}
    adm_headers = {"Authorization": auth_tokens["adm"]["Authorization"]}

    new_vasp_payload = {
        "entity_name": "TestVASP_India_Exchange",
        "chain": "ETH",
        "hot_wallet_addresses": ["0xTestVASP_HotWallet_1", "0xTestVASP_HotWallet_2"],
        "fiu_ind_registered": True,
        "sla_hours": 12.0,
        "nodal_contact": "nodal@testvasp.in",
    }

    # 1. Investigator attempt -> 403 Forbidden
    denied_res = client.post("/api/admin/vasps", json=new_vasp_payload, headers=inv_headers)
    assert denied_res.status_code == 403

    # 2. Admin creates VASP -> 201 Created
    create_res = client.post("/api/admin/vasps", json=new_vasp_payload, headers=adm_headers)
    assert create_res.status_code == 201
    assert create_res.json()["entity_name"] == "TestVASP_India_Exchange"

    # 3. Admin updates VASP details -> 200 OK
    update_res = client.put(
        "/api/admin/vasps/TestVASP_India_Exchange",
        json={"sla_hours": 6.0, "nodal_contact": "urgent.nodal@testvasp.in"},
        headers=adm_headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["sla_hours"] == 6.0
    assert update_res.json()["nodal_contact"] == "urgent.nodal@testvasp.in"

    # 4. Query single VASP
    get_res = client.get("/api/admin/vasps/TestVASP_India_Exchange", headers=inv_headers)
    assert get_res.status_code == 200
    assert get_res.json()["nodal_contact"] == "urgent.nodal@testvasp.in"

    # 5. Admin deletes VASP -> 200 OK
    del_res = client.delete("/api/admin/vasps/TestVASP_India_Exchange", headers=adm_headers)
    assert del_res.status_code == 200


# ==============================================================================
# 4. Police Intel Exchange Tests (Hash-and-RBAC)
# ==============================================================================

def test_police_intel_exchange_hash_and_rbac_privacy(auth_tokens):
    """Verifies Hash-and-RBAC architecture: client hashes address, exchange never accepts raw address."""
    headers = {"Authorization": auth_tokens["inv"]["Authorization"]}

    raw_suspect_address = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    # Compute client-side SHA-256 digest of canonical address
    client_computed_hash = hashlib.sha256(raw_suspect_address.strip().lower().encode("utf-8")).hexdigest()

    # 1. Attempt submitting raw wallet address -> Rejection (400 Bad Request)
    raw_sub_res = client.post(
        "/api/intel/submit",
        json={"address_hash": raw_suspect_address, "tag": "MULE_ACCOUNT", "district": "New Delhi"},
        headers=headers,
    )
    assert raw_sub_res.status_code == 400
    assert "Invalid address_hash" in raw_sub_res.json()["detail"]

    # 2. Submit valid SHA-256 digest
    valid_sub_res = client.post(
        "/api/intel/submit",
        json={
            "address_hash": client_computed_hash,
            "tag": "DIGITAL_ARREST_MULE",
            "district": "Cyber Crime Unit Delhi",
        },
        headers=headers,
    )
    assert valid_sub_res.status_code == 201
    assert valid_sub_res.json()["address_hash"] == client_computed_hash
    assert valid_sub_res.json()["tag"] == "DIGITAL_ARREST_MULE"

    # 3. Lookup client-side hashed address
    lookup_res = client.post(
        "/api/intel/lookup",
        json={"address_hash": client_computed_hash},
        headers=headers,
    )
    assert lookup_res.status_code == 200
    data = lookup_res.json()
    assert data["match_found"] is True
    assert data["address_hash"] == client_computed_hash
    assert len(data["tags"]) >= 1
    assert data["tags"][0]["tag"] == "DIGITAL_ARREST_MULE"
    # Verify Hash-and-RBAC notice
    assert "Hash-and-RBAC" in data["architecture_notice"]


# ==============================================================================
# 5. "Arjuna" AI Co-pilot Tests (Factual Containment & Bilingual Summaries)
# ==============================================================================

def test_arjuna_copilot_strict_factual_summary_en_and_hi(auth_tokens):
    """Verifies that Arjuna produces prosecution summaries in English & Hindi with 100% factual containment."""
    headers = {"Authorization": auth_tokens["inv"]["Authorization"]}

    # Create a demo case with known parameters
    case_res = client.post(
        "/api/cases",
        json={
            "ncrp_ref": "NCRP/2026/ARJUNA-VERIFY-01",
            "victim_utr": "UPI-ARJUNA-8844",
            "amount_inr": 1125000.0,
            "suspect_address": "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
            "chain": "ETH",
        },
        headers=headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["case_id"]

    # Generate Arjuna summary
    summary_res = client.post(f"/api/analysis/{case_id}/arjuna-summary", headers=headers)
    assert summary_res.status_code == 200
    data = summary_res.json()

    assert data["case_id"] == case_id
    assert data["ncrp_ref"] == "NCRP/2026/ARJUNA-VERIFY-01"
    assert data["strict_containment_passed"] is True

    # English summary validation
    summary_en = data["summary_en"]
    assert "NCRP/2026/ARJUNA-VERIFY-01" in summary_en
    assert "UPI-ARJUNA-8844" in summary_en
    assert "1,125,000.00" in summary_en or "1125000" in summary_en
    assert "Section 94 BNSS" in summary_en

    # Hindi summary validation
    summary_hi = data["summary_hi"]
    assert "NCRP/2026/ARJUNA-VERIFY-01" in summary_hi
    assert "UPI-ARJUNA-8844" in summary_hi
    assert "धारा 94" in summary_hi  # Section 94 BNSS in Hindi
