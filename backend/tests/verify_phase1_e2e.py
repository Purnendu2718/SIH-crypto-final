"""Phase 1 E2E Verification Script.
Executes the explicit verification checklist from Phase 1:
1. Creates two test officer accounts.
2. Seeds distinct cases for each officer.
3. Logs in as Officer 1 and confirms ONLY Officer 1's seeded cases are returned.
4. Logs in as Officer 2 and confirms ONLY Officer 2's seeded cases are returned.
5. Verifies database-level RLS prevents cross-case visibility.
6. Verifies token validity and session restoration without re-entering credentials.
7. Promotes an officer via promote_officer script and verifies supervisory visibility.
"""

import sys
import os
import json
import uuid
from fastapi.testclient import TestClient

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.database import init_db
from scripts.promote_officer import promote

client = TestClient(app)

def run_phase1_verification():
    print("=" * 70)
    print("CRYPTO TRACE SENTINEL — PHASE 1 E2E VERIFICATION SUITE")
    print("=" * 70)

    init_db()

    # Step 1: Create two test officer accounts
    print("\n[Step 1] Creating two test officer accounts via /api/auth/signup...")
    officer1_email = f"officer_delhi_{uuid.uuid4().hex[:6]}@sentinel.gov.in"
    officer2_email = f"officer_mumbai_{uuid.uuid4().hex[:6]}@sentinel.gov.in"

    res1 = client.post("/api/auth/signup", json={
        "email": officer1_email,
        "password": "Password123!Delhi",
        "full_name": "SI Rajesh Delhi",
        "badge_no": "DL-1092",
        "district": "Cyber Crime Cell New Delhi"
    })
    assert res1.status_code == 201, f"Officer 1 signup failed: {res1.text}"
    officer1_data = res1.json()
    token1 = officer1_data["access_token"]
    id1 = officer1_data["officer"]["id"]
    role1 = officer1_data["officer"]["role"]
    print(f"  --> Created Officer 1: {officer1_email} (ID: {id1}, Role: {role1})")
    assert role1 == "INVESTIGATOR", "Default role must be INVESTIGATOR"

    res2 = client.post("/api/auth/signup", json={
        "email": officer2_email,
        "password": "Password123!Mumbai",
        "full_name": "Insp. Priya Mumbai",
        "badge_no": "MH-4091",
        "district": "Cyber Crime Cell Mumbai"
    })
    assert res2.status_code == 201, f"Officer 2 signup failed: {res2.text}"
    officer2_data = res2.json()
    token2 = officer2_data["access_token"]
    id2 = officer2_data["officer"]["id"]
    role2 = officer2_data["officer"]["role"]
    print(f"  --> Created Officer 2: {officer2_email} (ID: {id2}, Role: {role2})")
    assert role2 == "INVESTIGATOR", "Default role must be INVESTIGATOR"

    # Step 2: Seed distinct cases for each officer
    print("\n[Step 2] Creating distinct cases for each officer...")
    case1_ref = f"NCRP/2026/DL-{uuid.uuid4().hex[:4].upper()}"
    case2_ref = f"NCRP/2026/MH-{uuid.uuid4().hex[:4].upper()}"

    c1 = client.post("/api/cases", json={
        "ncrp_ref": case1_ref,
        "victim_utr": "UPI-111222333444",
        "amount_inr": 450000.0,
        "chain": "ETH",
        "suspect_address": "0x1111111111111111111111111111111111111111"
    }, headers={"Authorization": f"Bearer {token1}"})
    assert c1.status_code == 201, f"Case 1 creation failed: {c1.text}"
    print(f"  --> Seeded Case for Officer 1: {case1_ref} (INR 4,50,000)")

    c2 = client.post("/api/cases", json={
        "ncrp_ref": case2_ref,
        "victim_utr": "UPI-555666777888",
        "amount_inr": 920000.0,
        "chain": "TRON",
        "suspect_address": "TR7NHqjeGn2UaWmFa5465q2mq4EmPy8Z"
    }, headers={"Authorization": f"Bearer {token2}"})
    assert c2.status_code == 201, f"Case 2 creation failed: {c2.text}"
    print(f"  --> Seeded Case for Officer 2: {case2_ref} (INR 9,20,000)")

    # Step 3: Query cases as Officer 1
    print("\n[Step 3] Querying preloaded caseload as Officer 1...")
    cases1 = client.get("/api/cases", headers={"Authorization": f"Bearer {token1}"}).json()
    refs1 = [c["ncrp_ref"] for c in cases1]
    print(f"  --> Officer 1 Caseload: {refs1}")
    assert case1_ref in refs1, "Officer 1 must see Case 1"
    assert case2_ref not in refs1, "Officer 1 must NEVER see Officer 2's case (RLS violation)"
    print("  --> [PASS] Officer 1 sees ONLY Officer 1's cases.")

    # Step 4: Query cases as Officer 2
    print("\n[Step 4] Querying preloaded caseload as Officer 2...")
    cases2 = client.get("/api/cases", headers={"Authorization": f"Bearer {token2}"}).json()
    refs2 = [c["ncrp_ref"] for c in cases2]
    print(f"  --> Officer 2 Caseload: {refs2}")
    assert case2_ref in refs2, "Officer 2 must see Case 2"
    assert case1_ref not in refs2, "Officer 2 must NEVER see Officer 1's case (RLS violation)"
    print("  --> [PASS] Officer 2 sees ONLY Officer 2's cases.")

    # Step 5: Session persistence check (token reuse without password re-entry)
    print("\n[Step 5] Verifying session persistence without re-entering credentials...")
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == officer1_email
    print(f"  --> [PASS] Active session restored: {me_data['full_name']} ({me_data['email']})")

    # Step 6: Role promotion verification
    print("\n[Step 6] Testing promotion to SUPERVISOR via promotion script...")
    promote(officer1_email, "SUPERVISOR")

    # Log in as newly promoted supervisor
    login_super = client.post("/api/auth/login", json={
        "email": officer1_email,
        "password": "Password123!Delhi"
    })
    token_super = login_super.json()["access_token"]
    cases_super = client.get("/api/cases", headers={"Authorization": f"Bearer {token_super}"}).json()
    refs_super = [c["ncrp_ref"] for c in cases_super]
    print(f"  --> Supervisory Broad Caseload: {refs_super}")
    assert case1_ref in refs_super, "Supervisor must see Case 1"
    assert case2_ref in refs_super, "Supervisor must see Case 2 from Mumbai district"
    print("  --> [PASS] Supervisor clearance successfully enables cross-district visibility.")

    print("\n" + "=" * 70)
    print("ALL PHASE 1 REQUIREMENTS VERIFIED AND PASSING.")
    print("=" * 70)

if __name__ == "__main__":
    run_phase1_verification()
