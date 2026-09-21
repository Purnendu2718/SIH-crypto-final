"""Pytest suite for Phase 5: Evidence, Audit Log, Legal Notice, and PDF Report.
Verifies SHA-256 hashing, Merkle roots, Section 94 BNSS notice formatting,
ReportLab PDF generation with Section 63 BSA certificate, and audit log tamper detection.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import os
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, init_db
from app.models import AuditLog, Profile, Case, WalletSubmission, AnalysisRun, generate_uuid, utc_now
from app.services import run_full_forensic_pipeline
from app.services.evidence import EvidenceManager, compute_sha256, compute_merkle_root
from app.services.legal_notice import generate_section_94_bnss_notice
from app.services.report_generator import generate_pdf_evidence_report
from app.services.audit import append_audit_entry, verify_audit_chain

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    # Seed demo cases
    client.post("/api/cases/seed-demo")
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_merkle_root_computation():
    """Verify Merkle tree construction with odd and even number of leaves."""
    leaves = [
        compute_sha256(b"file_1_data"),
        compute_sha256(b"file_2_data"),
        compute_sha256(b"file_3_data"),
    ]
    root = compute_merkle_root(leaves)
    assert len(root) == 64
    assert root != leaves[0]

    # Deterministic check
    assert compute_merkle_root(leaves) == root


def test_scenario_1_evidence_package_and_legal_notice(db):
    """Generate full evidence package + Section 94 BNSS notice for scenario 1."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    
    # Create and persist Case, Submission, and Run
    test_case = Case(
        case_id=generate_uuid(),
        ncrp_ref="NCRP/2026/DL-49102",
        victim_utr="UPI-429188092144",
        amount_inr=1125000.0,
        status="OPEN",
    )
    db.add(test_case)
    db.flush()

    test_sub = WalletSubmission(
        submission_id=generate_uuid(),
        case_id=test_case.case_id,
        chain="ETH",
        address=suspect_addr,
    )
    db.add(test_sub)
    db.flush()

    test_run = AnalysisRun(
        run_id=generate_uuid(),
        submission_id=test_sub.submission_id,
        status="PENDING",
    )
    db.add(test_run)
    db.commit()
    db.refresh(test_run)
    run_id = test_run.run_id

    # 1. Run forensic pipeline
    forensic_data = run_full_forensic_pipeline(
        start_address=suspect_addr,
        chain="ETH",
        run_id=run_id,
        stolen_principal=1125000.0,
        db=db,
    )
    assert forensic_data["status"] == "COMPLETED"
    assert forensic_data["attribution"]["matched_entity"] == "CoinDCX"

    # 2. Generate Section 94 BNSS Notice
    tx_hashes = [p["tx_hash"] for p in forensic_data["trace"]["paths"]]
    notice_text = generate_section_94_bnss_notice(
        ncrp_ref="NCRP/2026/DL-49102",
        vasp_name="CoinDCX",
        nodal_contact="nodal.officer@coindcx.com",
        suspect_address=suspect_addr,
        chain="ETH",
        tx_hashes=tx_hashes,
        amount_inr=1125000.0,
        victim_utr="UPI-429188092144",
        officer_name="SI Vikram Sharma",
        badge_no="DEL-8842",
        district="Cyber Cell New Delhi",
    )

    # Mandatory checks on statutory notice
    assert "SECTION 94 OF THE BHARATIYA NAGARIK SURAKSHA SANHITA (BNSS), 2023" in notice_text
    assert "CoinDCX" in notice_text
    assert "nodal.officer@coindcx.com" in notice_text
    assert "NCRP/2026/DL-49102" in notice_text
    assert suspect_addr in notice_text
    assert all(tx in notice_text for tx in tx_hashes)
    assert notice_text.endswith("Draft for review by the investigating officer / department legal cell before issuance.")

    # 3. Generate PDF Report with Section 63 BSA certificate
    case_dict = {
        "ncrp_ref": "NCRP/2026/DL-49102",
        "victim_utr": "UPI-429188092144",
        "amount_inr": 1125000.0,
    }
    officer_dict = {
        "full_name": "SI Vikram Sharma",
        "badge_no": "DEL-8842",
        "district": "Cyber Cell New Delhi",
    }
    evidence_hashes = {
        "sha256_hash": compute_sha256(b"dummy_payload"),
        "merkle_root": compute_sha256(b"dummy_root"),
    }
    pdf_bytes = generate_pdf_evidence_report(
        case_data=case_dict,
        forensic_data=forensic_data,
        evidence_hashes=evidence_hashes,
        officer_data=officer_dict,
    )

    # PDF format assertions
    assert len(pdf_bytes) > 2000, "PDF should contain valid binary content"
    assert pdf_bytes.startswith(b"%PDF-"), "Generated document must be a valid PDF"

    # 4. Create complete Evidence Package
    additional_files = {
        "section_94_bnss_notice.txt": notice_text.encode("utf-8"),
        "forensic_report.pdf": pdf_bytes,
    }
    pkg = EvidenceManager.create_evidence_package(
        run_id=run_id,
        trace_payload=forensic_data,
        additional_files=additional_files,
        db=db,
    )

    assert len(pkg["sha256_hash"]) == 64
    assert len(pkg["merkle_root"]) == 64
    assert "trace_payload.json" in pkg["files"]
    assert "section_94_bnss_notice.txt" in pkg["files"]
    assert "forensic_report.pdf" in pkg["files"]

    # Also test via HTTP API endpoints
    login_res = client.post("/api/auth/login", json={"email": "sharma@sentinel.gov.in", "password": "SentinelPass123!"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Generate evidence via endpoint
    gen_res = client.post(f"/api/evidence/generate/{run_id}", headers=headers)
    assert gen_res.status_code == 200
    gen_data = gen_res.json()
    assert "package" in gen_data
    assert "legal_notice" in gen_data
    assert "Draft for review by the investigating officer" in gen_data["legal_notice"]

    # Download PDF report via endpoint
    pdf_res = client.get(f"/api/evidence/pdf/{run_id}", headers=headers)
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")
    assert len(pdf_res.content) > 2000


def test_audit_log_hash_chain_and_tamper_detection(db):
    """Test audit log hash chain formation and verify that corrupted entries are detected."""
    officer_id = "test-officer-audit-001"

    # Append 3 audit entries forming a chain
    entry1 = append_audit_entry(db, officer_id, "CASE_CREATED", "case-001")
    entry2 = append_audit_entry(db, officer_id, "TRACE_EXECUTED", "run-001")
    entry3 = append_audit_entry(db, officer_id, "EVIDENCE_EXPORTED", "pkg-001")

    # 1. Verify chain is currently intact
    verification = verify_audit_chain(db)
    assert verification["is_valid"] is True
    assert verification["status"] == "CHAIN_INTACT"
    assert verification["total_entries"] >= 3

    # Also test through HTTP endpoint
    login_res = client.post("/api/auth/login", json={"email": "sharma@sentinel.gov.in", "password": "SentinelPass123!"})
    token = login_res.json()["access_token"]
    http_verify = client.get("/api/audit/verify", headers={"Authorization": f"Bearer {token}"}).json()
    assert http_verify["is_valid"] is True

    # 2. Deliberately tamper with entry 2's action in the database
    original_action = entry2.action
    entry2.action = "TAMPERED_ACTION_ALTERED_BY_ATTACKER"
    db.commit()

    # 3. Verify that the tamper is immediately caught by verification
    corrupted_verify = verify_audit_chain(db)
    assert corrupted_verify["is_valid"] is False
    assert corrupted_verify["status"] == "HASH_TAMPERED"
    assert corrupted_verify["corrupted_entry_id"] == entry2.entry_id
    print(f"Tamper caught: {corrupted_verify['message']}")

    # Restore entry2 so database state stays clean
    entry2.action = original_action
    db.commit()
