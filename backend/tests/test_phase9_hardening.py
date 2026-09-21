"""Pytest suite for Phase 9: Hardening, Edge Cases, RBAC/RLS, Rate-Limiting, and Security.
Verifies:
1. Edge cases: Empty trace, malformed addresses, SQL/XSS injection attempts, hop budget exhaustion.
2. Burn/null addresses never attributed as off-ramps.
3. Dust filtering boundaries (zero vs extreme thresholds).
4. Rate-limiting on public-facing endpoints (HTTP 429 with Retry-After).
5. Strict RBAC & RLS isolation: Investigator cannot access other officers' cases, runs, evidence, or watchlists.
6. Secret auditing: .env.example contains only placeholders.

Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 9.
"""

import pytest
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Profile, Case, WalletSubmission, AnalysisRun, generate_uuid, utc_now
from app.security import hash_password
from app.services import run_full_forensic_pipeline
from app.services.address_validator import validate_and_detect_chain
from app.services.trace_engine import TraceEngine
from app.middleware.rate_limiter import limiter

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_environment():
    init_db()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def two_investigators(db):
    """Create two distinct investigators with isolated cases."""
    # Investigator Alpha
    alpha_id = generate_uuid()
    alpha_email = f"alpha_{uuid.uuid4().hex[:6]}@sentinel.gov.in"
    alpha = Profile(
        id=alpha_id,
        email=alpha_email,
        password_hash=hash_password("Pass123!Alpha"),
        full_name="Officer Alpha",
        role="INVESTIGATOR",
        district="Delhi South",
    )
    db.add(alpha)

    # Investigator Beta
    beta_id = generate_uuid()
    beta_email = f"beta_{uuid.uuid4().hex[:6]}@sentinel.gov.in"
    beta = Profile(
        id=beta_id,
        email=beta_email,
        password_hash=hash_password("Pass123!Beta"),
        full_name="Officer Beta",
        role="INVESTIGATOR",
        district="Mumbai North",
    )
    db.add(beta)
    db.flush()

    # Case for Alpha
    case_alpha = Case(
        case_id=generate_uuid(),
        ncrp_ref=f"NCRP/2026/ALPHA-{uuid.uuid4().hex[:4]}",
        assigned_officer_id=alpha.id,
        status="OPEN",
    )
    db.add(case_alpha)
    db.flush()

    sub_alpha = WalletSubmission(
        submission_id=generate_uuid(),
        case_id=case_alpha.case_id,
        chain="ETH",
        address="0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
    )
    db.add(sub_alpha)
    db.flush()

    run_alpha = AnalysisRun(
        run_id=generate_uuid(),
        submission_id=sub_alpha.submission_id,
        status="COMPLETED",
        completed_at=utc_now(),
    )
    db.add(run_alpha)

    # Case for Beta
    case_beta = Case(
        case_id=generate_uuid(),
        ncrp_ref=f"NCRP/2026/BETA-{uuid.uuid4().hex[:4]}",
        assigned_officer_id=beta.id,
        status="OPEN",
    )
    db.add(case_beta)
    db.flush()

    sub_beta = WalletSubmission(
        submission_id=generate_uuid(),
        case_id=case_beta.case_id,
        chain="ETH",
        address="0x3a9F784260D672b15Fa0e20f18837138096c7B22",
    )
    db.add(sub_beta)
    db.flush()

    run_beta = AnalysisRun(
        run_id=generate_uuid(),
        submission_id=sub_beta.submission_id,
        status="COMPLETED",
        completed_at=utc_now(),
    )
    db.add(run_beta)
    db.commit()

    # Get JWT tokens
    res_alpha = client.post("/api/auth/login", json={"email": alpha_email, "password": "Pass123!Alpha"})
    token_alpha = res_alpha.json()["access_token"]

    res_beta = client.post("/api/auth/login", json={"email": beta_email, "password": "Pass123!Beta"})
    token_beta = res_beta.json()["access_token"]

    return {
        "alpha": {"id": alpha.id, "email": alpha_email, "token": token_alpha, "case": case_alpha, "sub": sub_alpha, "run": run_alpha},
        "beta": {"id": beta.id, "email": beta_email, "token": token_beta, "case": case_beta, "sub": sub_beta, "run": run_beta},
    }


# ---------------------------------------------------------------------------
# Test 1: Edge Cases — Malformed Addresses & Injection Attacks
# ---------------------------------------------------------------------------
def test_malformed_and_injection_addresses_cleanly_rejected(db):
    """Ensure malformed addresses, SQL injection strings, and XSS payloads fail validation gracefully."""
    attack_payloads = [
        "' OR 1=1; --",
        "0x' UNION SELECT * FROM profiles; --",
        "<script>alert('xss')</script>",
        "0x123",  # Too short
        "0xZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",  # Invalid hex
        "1InvalidBase58AddressWithBadChecksum999",
        "TR7InvalidTronChecksumAddress9999999999",
        "",  # Empty string
        "   ",  # Whitespace
        "0x0",  # Truncated null
    ]

    for payload in attack_payloads:
        is_valid, chain, err = validate_and_detect_chain(payload)
        assert not is_valid, f"Expected '{payload}' to be rejected"
        assert chain == "UNRECOGNIZED_ADDRESS_FORMAT"

        # Forensic pipeline must handle cleanly without 500 error
        res = run_full_forensic_pipeline(start_address=payload, chain="ETH", db=db)
        assert res["status"] == "ANALYSIS_FAILED_INVALID_ADDRESS"
        assert res["attribution"]["rule_fired"] == "UNRECOGNIZED_ADDRESS_FORMAT"
        assert res["attribution"]["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Test 2: Edge Cases — Empty Trace (Inactive / Zero-Tx Wallet)
# ---------------------------------------------------------------------------
def test_empty_trace_returns_clean_insufficient_evidence(db):
    """An address with no transactions must terminate cleanly with NO_PATH_FOUND and 0.0 confidence."""
    empty_addr = "0x0000000000000000000000000000000000000001"
    res = run_full_forensic_pipeline(start_address=empty_addr, chain="ETH", db=db)

    assert res["status"] == "ANALYSIS_COMPLETE_NO_PATH_FOUND"
    assert res["attribution"]["matched_entity"] == "Insufficient Evidence"
    assert res["attribution"]["confidence"] == 0.0
    assert res["attribution"]["confidence_band"] == "INSUFFICIENT_EVIDENCE"
    assert res["attribution"]["rule_fired"] in ("NO_PATH_DETECTED", "UNVERIFIED_CLUSTER_INSUFFICIENT_EVIDENCE")
    assert len(res["trace"]["paths"]) == 0


# ---------------------------------------------------------------------------
# Test 3: Edge Cases — Burn & Null Address Safety
# ---------------------------------------------------------------------------
def test_burn_and_null_addresses_never_attributed(db):
    """Burn and zero addresses must never be attributed as an exchange or off-ramp."""
    burn_addresses = [
        "0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead",
    ]

    for addr in burn_addresses:
        res = run_full_forensic_pipeline(start_address=addr, chain="ETH", db=db)
        assert res["attribution"]["matched_entity"] == "Insufficient Evidence"
        assert res["attribution"]["rule_fired"] == "NO_PATH_DETECTED"
        assert res["attribution"]["confidence"] == 0.0
        assert res["attribution"]["confidence_band"] == "INSUFFICIENT_EVIDENCE"


# ---------------------------------------------------------------------------
# Test 4: Edge Cases — Hop Budget Exhaustion & No Fabrication
# ---------------------------------------------------------------------------
def test_hop_budget_exhaustion_boundary(db):
    """When hop budget is constrained, trace terminates with NO_CONFIDENT_OFF_RAMP and zero fabricated entities."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"

    # Constrained to 0 hops
    engine_0 = TraceEngine(max_hops=0)
    res_0 = engine_0.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db)
    assert res_0.total_hops == 0
    assert res_0.status == "NO_CONFIDENT_OFF_RAMP"
    assert res_0.matched_entity is None

    # Constrained to 1 hop (Scenario 1 needs 2 hops to reach CoinDCX)
    engine_1 = TraceEngine(max_hops=1)
    res_1 = engine_1.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db)
    assert res_1.total_hops == 1
    assert res_1.status == "NO_CONFIDENT_OFF_RAMP"
    assert res_1.matched_entity is None


# ---------------------------------------------------------------------------
# Test 5: Edge Cases — Extreme Dust Thresholds
# ---------------------------------------------------------------------------
def test_dust_filtering_extremes(db):
    """Ensure dust thresholds of 0.0 and 1000.0 ETH behave deterministically."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"

    # Threshold 0.0 allows all transfers
    engine_zero = TraceEngine(dust_threshold=0.0)
    res_zero = engine_zero.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db)
    assert res_zero.status == "COMPLETED"
    assert res_zero.total_hops >= 2

    # High threshold filters all normal transfers
    engine_high = TraceEngine(dust_threshold=1000.0)
    res_high = engine_high.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db)
    assert res_high.status == "NO_CONFIDENT_OFF_RAMP"
    assert res_high.total_hops == 0


# ---------------------------------------------------------------------------
# Test 6: Rate Limiting on Public Endpoints (HTTP 429)
# ---------------------------------------------------------------------------
def test_rate_limiter_triggers_429_on_burst():
    """Rapid repeated requests to /api/auth/login trigger HTTP 429 Too Many Requests with Retry-After header."""
    limiter.reset()

    # Login rate limit is 10 requests per minute
    test_ip = "192.168.1.100"
    headers = {"X-Forwarded-For": test_ip}

    # First 10 requests should proceed
    for i in range(10):
        res = client.post(
            "/api/auth/login",
            json={"email": "nonexistent@sentinel.gov.in", "password": "WrongPassword123!"},
            headers=headers,
        )
        assert res.status_code in (401, 200)

    # 11th request must be blocked with HTTP 429
    burst_res = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@sentinel.gov.in", "password": "WrongPassword123!"},
        headers=headers,
    )
    assert burst_res.status_code == 429
    assert "Rate limit exceeded" in burst_res.json()["error"]
    assert "Retry-After" in burst_res.headers
    assert int(burst_res.headers["Retry-After"]) > 0

    limiter.reset()


# ---------------------------------------------------------------------------
# Test 7: Strict Cross-Officer RBAC & RLS Isolation
# ---------------------------------------------------------------------------
def test_cross_officer_rls_isolation(two_investigators):
    """Investigator Alpha cannot view, analyze, generate evidence for, or manage Investigator Beta's case."""
    alpha = two_investigators["alpha"]
    beta = two_investigators["beta"]

    headers_alpha = {"Authorization": f"Bearer {alpha['token']}"}
    headers_beta = {"Authorization": f"Bearer {token_beta}" if (token_beta := beta["token"]) else ""}

    # 1. Alpha attempts to view Beta's case -> 404 / Unauthorized under current clearance
    res = client.get(f"/api/cases/{beta['case'].case_id}", headers=headers_alpha)
    assert res.status_code == 404

    # 2. Alpha attempts to run analysis on Beta's submission -> 403 Forbidden
    res = client.post(f"/api/analysis/run/{beta['sub'].submission_id}", headers=headers_alpha)
    assert res.status_code == 403

    # 3. Alpha attempts to get analysis report for Beta's run -> 403 Forbidden
    res = client.get(f"/api/analysis/run/{beta['run'].run_id}", headers=headers_alpha)
    assert res.status_code == 403

    # 4. Alpha attempts to generate evidence package for Beta's run -> 403 Forbidden
    res = client.post(f"/api/evidence/generate/{beta['run'].run_id}", headers=headers_alpha)
    assert res.status_code == 403

    # 5. Alpha attempts to download PDF evidence for Beta's run -> 403 Forbidden
    res = client.get(f"/api/evidence/pdf/{beta['run'].run_id}", headers=headers_alpha)
    assert res.status_code == 403

    # 6. Alpha attempts to add watchlist entry to Beta's case -> 403 Forbidden
    res = client.post(
        "/api/watchlist",
        json={"address": "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A", "chain": "ETH", "case_id": beta["case"].case_id},
        headers=headers_alpha,
    )
    assert res.status_code == 403


def test_supervisor_sees_all_investigators_cases(two_investigators):
    """Supervisors possess cross-department clearance to inspect any officer's case."""
    # Login as supervisor (Verma)
    res = client.post(
        "/api/auth/login",
        json={"email": "verma@sentinel.gov.in", "password": "SentinelPass123!"},
    )
    assert res.status_code == 200
    sup_token = res.json()["access_token"]
    headers_sup = {"Authorization": f"Bearer {sup_token}"}

    # Supervisor can view Beta's case
    beta_case_id = two_investigators["beta"]["case"].case_id
    res_beta = client.get(f"/api/cases/{beta_case_id}", headers=headers_sup)
    assert res_beta.status_code == 200

    # Supervisor can view Alpha's case
    alpha_case_id = two_investigators["alpha"]["case"].case_id
    res_alpha = client.get(f"/api/cases/{alpha_case_id}", headers=headers_sup)
    assert res_alpha.status_code == 200


# ---------------------------------------------------------------------------
# Test 8: Secret Audit — .env.example Contains Only Placeholders
# ---------------------------------------------------------------------------
def test_env_example_contains_no_real_secrets():
    """Confirm .env.example has zero actual secret keys committed."""
    import os
    env_example_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env.example"))
    assert os.path.exists(env_example_path), ".env.example must exist at repo root"

    with open(env_example_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must contain placeholder keywords
    assert "placeholder-anon-key" in content
    assert "placeholder-service-role-key" in content
    assert "YOUR_ALCHEMY_KEY" in content

    # Must NOT contain real credentials
    assert "AIzaSy" not in content  # Real Google API key prefix
    assert "0x" not in content or "0x..." in content or "0x" not in content.replace("YOUR_ALCHEMY_KEY", "")
    assert "ghp_" not in content    # GitHub personal access token
    assert "sk_live" not in content # Stripe live key
