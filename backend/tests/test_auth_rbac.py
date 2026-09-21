"""Automated tests for Officer Auth, JWT Verification, RBAC, and Caseload Preload RLS."""

import uuid
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()
    # Seed demo cases
    client.post("/api/cases/seed-demo")
    yield


def test_unauthenticated_cases_request_fails():
    """Ensure accessing protected cases endpoint without token returns 401."""
    response = client.get("/api/cases")
    assert response.status_code == 401


def test_officer_signup_defaults_to_investigator():
    """Ensure new signup automatically defaults to INVESTIGATOR role."""
    unique_email = f"investigator_{uuid.uuid4().hex[:8]}@sentinel.gov.in"
    signup_payload = {
        "email": unique_email,
        "password": "SecurePassword123!",
        "full_name": "Test Officer Kumar",
        "badge_no": "TEST-101",
        "district": "Cyber Cell Punjab",
    }
    response = client.post("/api/auth/signup", json=signup_payload)
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["officer"]["role"] == "INVESTIGATOR"
    assert data["officer"]["email"] == unique_email


def test_investigator_rls_isolation():
    """Confirm Investigator Sharma ONLY sees Sharma's cases, not Patel's."""
    # 1. Login as Sharma
    sharma_login = client.post(
        "/api/auth/login",
        json={"email": "sharma@sentinel.gov.in", "password": "SentinelPass123!"},
    )
    assert sharma_login.status_code == 200
    sharma_token = sharma_login.json()["access_token"]
    sharma_id = sharma_login.json()["officer"]["id"]

    # 2. Login as Patel
    patel_login = client.post(
        "/api/auth/login",
        json={"email": "patel@sentinel.gov.in", "password": "SentinelPass123!"},
    )
    assert patel_login.status_code == 200
    patel_token = patel_login.json()["access_token"]
    patel_id = patel_login.json()["officer"]["id"]

    # 3. Query cases as Sharma
    sharma_cases_res = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {sharma_token}"},
    )
    assert sharma_cases_res.status_code == 200
    sharma_cases = sharma_cases_res.json()
    assert len(sharma_cases) >= 1
    for c in sharma_cases:
        assert c["assigned_officer_id"] == sharma_id
        # Confirm Sharma never sees Patel's NCRP ref
        assert "MH-82190" not in c["ncrp_ref"]

    # 4. Query cases as Patel
    patel_cases_res = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {patel_token}"},
    )
    assert patel_cases_res.status_code == 200
    patel_cases = patel_cases_res.json()
    assert len(patel_cases) >= 1
    for c in patel_cases:
        assert c["assigned_officer_id"] == patel_id
        # Confirm Patel never sees Sharma's NCRP ref
        assert "DL-49102" not in c["ncrp_ref"]


def test_supervisor_sees_all_cases():
    """Confirm Supervisor ACP Verma sees cases from all investigators."""
    verma_login = client.post(
        "/api/auth/login",
        json={"email": "verma@sentinel.gov.in", "password": "SentinelPass123!"},
    )
    assert verma_login.status_code == 200
    verma_token = verma_login.json()["access_token"]

    verma_cases_res = client.get(
        "/api/cases",
        headers={"Authorization": f"Bearer {verma_token}"},
    )
    assert verma_cases_res.status_code == 200
    verma_cases = verma_cases_res.json()
    # Verma should see at least both Sharma's and Patel's cases
    refs = [c["ncrp_ref"] for c in verma_cases]
    assert any("DL-49102" in r for r in refs)
    assert any("MH-82190" in r for r in refs)


def test_role_promotion():
    """Test promoting an investigator to supervisor expands their access."""
    # Create an investigator with unique email
    email = f"promo_{uuid.uuid4().hex[:8]}@sentinel.gov.in"
    client.post(
        "/api/auth/signup",
        json={
            "email": email,
            "password": "Pass123!Promo",
            "full_name": "Promo Officer",
            "badge_no": "PR-01",
        },
    )
    login_res = client.post("/api/auth/login", json={"email": email, "password": "Pass123!Promo"})
    token = login_res.json()["access_token"]

    # Initially has 0 assigned cases
    cases_before = client.get("/api/cases", headers={"Authorization": f"Bearer {token}"}).json()
    assert len(cases_before) == 0

    # Promote to SUPERVISOR
    promo_res = client.post("/api/auth/promote", json={"email": email, "role": "SUPERVISOR"})
    assert promo_res.status_code == 200
    assert promo_res.json()["role"] == "SUPERVISOR"

    # Re-login to get updated token
    updated_login = client.post("/api/auth/login", json={"email": email, "password": "Pass123!Promo"})
    updated_token = updated_login.json()["access_token"]

    # Now as SUPERVISOR, can see all department cases
    cases_after = client.get("/api/cases", headers={"Authorization": f"Bearer {updated_token}"}).json()
    assert len(cases_after) >= 2
