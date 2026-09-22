"""Unit and integration test suite for Phase 10: Statutory Notice & Email Drafter with Approval Workflow.
Verifies:
1. RBAC & clearance rules: Investigators CANNOT approve notices (HTTP 403); only Supervisor/Admin can.
2. Safe dry-run email dispatch: MAIL_DRY_RUN=True writes .eml files to ./outbox with headers & attachments.
3. Jinja2 template autoescaping: Prevents script injection and unescaped HTML execution.
4. Evidentiary integrity guard: Polishing is rejected and discarded if hashes, addresses, dates, or amounts change.
5. Automated overdue reminders: Follow-up scanner creates DRAFT notices only; reminders are never auto-sent.
6. EML and ReportLab PDF download endpoints return valid MIME payloads.
7. Recipient directory loads placeholder exchange contacts without real personal contact details.

Reference: Phase 10 — Notice and email drafter with approval workflow, SIH26183.
"""

import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal, init_db
from app.models import Profile, Case, WalletSubmission, Notice, NoticeEvent, AuditLog, generate_uuid, utc_now
from app.security import create_access_token, hash_password
from app.services.notice_service import (
    render_notice_template,
    verify_polish_integrity,
    polish_notice_tone,
    generate_eml,
    generate_notice_pdf,
    dispatch_notice,
    check_and_create_overdue_reminders,
    get_exchange_contacts,
    DEFAULT_LEGAL_BASIS,
)


client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
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
def officers(db):
    """Create distinct investigator and supervisor profiles with access tokens."""
    inv_id = generate_uuid()
    investigator = Profile(
        id=inv_id,
        email=f"investigator_{inv_id[:6]}@cybercrime.gov.in",
        password_hash=hash_password("Investigator123!"),
        full_name="Sub-Inspector Vikram Rathore",
        role="INVESTIGATOR",
        district="Cyber Crime Cell, New Delhi",
        badge_no="DEL-CYB-5521",
    )
    db.add(investigator)

    sup_id = generate_uuid()
    supervisor = Profile(
        id=sup_id,
        email=f"supervisor_{sup_id[:6]}@cybercrime.gov.in",
        password_hash=hash_password("Supervisor123!"),
        full_name="ACP Neha Deshmukh",
        role="SUPERVISOR",
        district="Cyber Crime Cell, New Delhi",
        badge_no="DEL-CYB-1002",
    )
    db.add(supervisor)
    db.commit()

    inv_token = create_access_token(investigator.id, investigator.email, investigator.role)
    sup_token = create_access_token(supervisor.id, supervisor.email, supervisor.role)

    return investigator, inv_token, supervisor, sup_token


@pytest.fixture
def sample_case(db, officers):
    """Create a sample cybercrime case for testing notice generation."""
    investigator, _, _, _ = officers
    case_id = generate_uuid()
    case = Case(
        case_id=case_id,
        ncrp_ref="NCRP/2026/NOTICES-TEST-01",
        amount_inr=500000.0,
        assigned_officer_id=investigator.id,
        status="OPEN",
    )
    db.add(case)
    db.flush()

    sub = WalletSubmission(
        submission_id=generate_uuid(),
        case_id=case_id,
        chain="ETH",
        address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
    )
    db.add(sub)
    db.commit()
    db.refresh(case)
    return case


# ==============================================================================
# 1. Recipient Directory Tests
# ==============================================================================

def test_exchange_contacts_directory_structure():
    """Verify data/exchange_contacts.example.json loads with fake placeholder domains (.invalid)."""
    contacts = get_exchange_contacts()
    assert len(contacts) >= 4, "Expected at least 4 Indian/global exchange contacts in example directory."

    for c in contacts:
        assert "exchange_name" in c
        assert "nodal_email" in c
        # Must strictly use .example.invalid or .invalid placeholders — never real contacts
        assert ".invalid" in c["nodal_email"], f"Email {c['nodal_email']} must use .invalid top-level domain."


# ==============================================================================
# 2. Template Rendering & HTML Autoescape Security Tests
# ==============================================================================

def test_template_escaping_prevents_injection():
    """Verify that Jinja2 autoescape is strictly enabled to prevent script injection in rendered notices."""
    malicious_context = {
        "recipient_name": "<script>alert('xss_attack')</script>Exchange Desk",
        "recipient_email": "compliance@exchange.example.invalid",
        "case_reference": "NCRP/<b>MALICIOUS</b>",
        "legal_basis_text": DEFAULT_LEGAL_BASIS,
        "addresses": ["0x742d35Cc6634C0532925a3b844Bc454e4438f44e"],
        "tx_hashes": ["0x" + "a" * 64],
        "officer_name": "Inspector <img src=x onerror=alert(1)>",
    }

    # Test preservation template
    subj_p, body_p = render_notice_template("preservation", malicious_context)
    assert "<script>" not in body_p
    assert "&lt;script&gt;" in body_p
    assert "<b>" not in body_p
    assert "&lt;b&gt;" in body_p
    assert "<img" not in body_p
    assert "&lt;img" in body_p

    # Test freeze template
    subj_f, body_f = render_notice_template("freeze", malicious_context)
    assert "<script>" not in body_f
    assert "&lt;script&gt;" in body_f


def test_template_rendering_default_legal_basis():
    """Verify template uses default BNSS wording without auto-citing specific sections."""
    context = {
        "recipient_name": "WazirX Compliance Desk",
        "recipient_email": "nodal-officer@wazirx.example.invalid",
        "case_reference": "NCRP/2026/TEST-42",
        "addresses": ["0x742d35Cc6634C0532925a3b844Bc454e4438f44e"],
        "tx_hashes": [],
    }
    _, body = render_notice_template("preservation", context)
    assert "Bharatiya Nagarik Suraksha Sanhita, 2023" in body
    assert "(section to be confirmed by the investigating officer)" in body


# ==============================================================================
# 3. Guarded Tone Polish & Hash Integrity Verification Tests
# ==============================================================================

def test_verify_polish_integrity_rejects_altered_hash():
    """Verify that if a tone polish alters a 64-character hash, it is strictly rejected."""
    original_text = (
        "Please freeze funds transferred via transaction hash "
        "0x1111111111111111111111111111111111111111111111111111111111111111 on 2024-08-15."
    )
    # Altered hash
    tampered_text = (
        "Kindly execute immediate debit-freeze on transaction "
        "0x2222222222222222222222222222222222222222222222222222222222222222 on 2024-08-15."
    )

    is_valid, err = verify_polish_integrity(original_text, tampered_text)
    assert is_valid is False
    assert "Hash integrity mismatch" in err


def test_verify_polish_integrity_rejects_altered_address():
    """Verify that if a tone polish alters an address, it is rejected."""
    original_text = "Target wallet address: 0x742d35Cc6634C0532925a3b844Bc454e4438f44e."
    tampered_text = "Target wallet address: 0x0000000000000000000000000000000000000000."

    is_valid, err = verify_polish_integrity(original_text, tampered_text)
    assert is_valid is False
    assert "Address integrity mismatch" in err


def test_verify_polish_integrity_accepts_clean_rephrase():
    """Verify that a legitimate rephrase preserving all addresses, hashes, dates, and amounts passes."""
    original_text = (
        "Directive to freeze address 0x742d35Cc6634C0532925a3b844Bc454e4438f44e and hash "
        "0x" + "a" * 64 + " on 2024-08-15 for 500,000 INR."
    )
    clean_rephrase = (
        "Official notice commanding debit-restraint for address 0x742d35Cc6634C0532925a3b844Bc454e4438f44e "
        "and transaction 0x" + "a" * 64 + " registered on 2024-08-15 totaling 500,000 INR."
    )

    is_valid, err = verify_polish_integrity(original_text, clean_rephrase)
    assert is_valid is True
    assert err is None


# ==============================================================================
# 4. Approval Workflow & RBAC Clearance Tests
# ==============================================================================

def test_workflow_investigator_cannot_approve(db, officers, sample_case):
    """Verify strict role rule: An investigator cannot approve notices; returns HTTP 403."""
    investigator, inv_token, supervisor, sup_token = officers

    # 1. Investigator creates draft notice
    create_payload = {
        "kind": "preservation",
        "recipient_name": "CoinDCX Nodal Desk",
        "recipient_email": "nodal-officer@coindcx.example.invalid",
        "fir_reference": "FIR 88/2026 PS Cyber Cell",
        "reply_deadline_hours": 48,
    }
    resp = client.post(
        f"/api/v1/cases/{sample_case.case_id}/notices",
        json=create_payload,
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert resp.status_code == 200, resp.text
    notice_id = resp.json()["id"]

    # 2. Investigator submits for approval (draft -> pending_approval)
    sub_resp = client.post(
        f"/api/v1/notices/{notice_id}/submit",
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert sub_resp.status_code == 200
    assert sub_resp.json()["status"] == "pending_approval"

    # 3. Investigator attempts to approve -> MUST FAIL with 403 Forbidden
    inv_approve_resp = client.post(
        f"/api/v1/notices/{notice_id}/approve",
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert inv_approve_resp.status_code == 403
    assert "Investigators cannot approve notices" in inv_approve_resp.json()["detail"]

    # 4. Supervisor approves -> SUCCEEDS (pending_approval -> approved)
    sup_approve_resp = client.post(
        f"/api/v1/notices/{notice_id}/approve",
        headers={"Authorization": f"Bearer {sup_token}"},
    )
    assert sup_approve_resp.status_code == 200
    assert sup_approve_resp.json()["status"] == "approved"

    # Verify Notice in DB has status 'approved' and approved_by = supervisor.id
    notice_db = db.query(Notice).filter(Notice.id == notice_id).first()
    assert notice_db.status == "approved"
    assert notice_db.approved_by == supervisor.id


# ==============================================================================
# 5. Safe Dry-Run Dispatch & Outbox EML Generation Tests
# ==============================================================================

def test_dry_run_writes_eml_to_outbox(db, officers, sample_case):
    """Verify that dispatching an approved notice in dry-run mode writes an .eml to outbox/."""
    _, _, supervisor, sup_token = officers

    temp_outbox = tempfile.mkdtemp()
    try:
        with patch.object(settings, "MAIL_DRY_RUN", True), patch.object(settings, "OUTBOX_DIR", temp_outbox):
            # 1. Create and approve notice
            create_payload = {
                "kind": "freeze",
                "recipient_name": "Binance Global Nodal Desk",
                "recipient_email": "nodal-liaison@binance.example.invalid",
                "reply_deadline_hours": 24,
            }
            create_resp = client.post(
                f"/api/v1/cases/{sample_case.case_id}/notices",
                json=create_payload,
                headers={"Authorization": f"Bearer {sup_token}"},
            )
            notice_id = create_resp.json()["id"]

            client.post(f"/api/v1/notices/{notice_id}/submit", headers={"Authorization": f"Bearer {sup_token}"})
            client.post(f"/api/v1/notices/{notice_id}/approve", headers={"Authorization": f"Bearer {sup_token}"})

            # 2. Dispatch notice (approved -> sent)
            send_resp = client.post(
                f"/api/v1/notices/{notice_id}/send",
                headers={"Authorization": f"Bearer {sup_token}"},
            )
            assert send_resp.status_code == 200, send_resp.text
            send_data = send_resp.json()
            assert send_data["status"] == "sent"
            assert send_data["dry_run"] is True

            # 3. Verify .eml file written in outbox
            expected_eml = Path(temp_outbox) / f"{notice_id}.eml"
            assert expected_eml.exists(), f"Expected EML file at {expected_eml}"

            eml_content = expected_eml.read_bytes()
            assert b"Subject:" in eml_content
            assert b"nodal-liaison@binance.example.invalid" in eml_content
            assert b"X-Case-Reference:" in eml_content
            assert b"X-Notice-ID:" in eml_content

            # 4. Verify NoticeEvent and AuditLog entries
            event = db.query(NoticeEvent).filter(NoticeEvent.notice_id == notice_id, NoticeEvent.event_type == "SENT").first()
            assert event is not None
            assert event.to_status == "sent"

            audit = db.query(AuditLog).filter(AuditLog.target_id == notice_id, AuditLog.action == "NOTICE_DISPATCHED_DRY_RUN").first()
            assert audit is not None
            assert audit.officer_id == supervisor.id
    finally:
        shutil.rmtree(temp_outbox, ignore_errors=True)


# ==============================================================================
# 6. Automated Follow-up Reminders (Drafts Only) Tests
# ==============================================================================

def test_reminders_are_drafts_only(db, officers, sample_case):
    """Verify that overdue sent notices produce reminder notices in DRAFT status only."""
    investigator, _, _, _ = officers

    # Create an overdue sent notice: due yesterday
    past_due = utc_now() - timedelta(days=1)
    past_sent = utc_now() - timedelta(days=3)

    notice_id = generate_uuid()
    overdue_notice = Notice(
        id=notice_id,
        case_id=sample_case.case_id,
        kind="preservation",
        recipient_name="ZebPay Compliance",
        recipient_email="nodal-officer@zebpay.example.invalid",
        subject="Statutory Notice for Preservation",
        body="Original preservation requisition text...",
        status="sent",
        created_by=investigator.id,
        due_at=past_due,
        sent_at=past_sent,
    )
    db.add(overdue_notice)
    db.commit()

    # Run follow-up scanner
    reminders = check_and_create_overdue_reminders(db)
    assert len(reminders) >= 1

    created_rem = next(r for r in reminders if r.recipient_email == "nodal-officer@zebpay.example.invalid")
    assert created_rem.kind == "reminder"
    # CRITICAL INVARIANT: Reminders MUST strictly be drafts, never auto-sent!
    assert created_rem.status == "draft"
    assert created_rem.approved_by is None
    assert "FINAL REMINDER" in created_rem.subject

    # Verify audit log recorded draft creation
    rem_audit = db.query(AuditLog).filter(AuditLog.target_id == created_rem.id, AuditLog.action == "REMINDER_NOTICE_DRAFT_CREATED").first()
    assert rem_audit is not None


# ==============================================================================
# 7. EML & ReportLab PDF Download Endpoints Tests
# ==============================================================================

def test_download_eml_and_pdf_endpoints(db, officers, sample_case):
    """Verify that EML and PDF downloads return valid MIME payloads with attachments."""
    _, inv_token, _, _ = officers

    # Create draft notice
    create_payload = {
        "kind": "preservation",
        "recipient_name": "Mudrex Compliance Desk",
        "recipient_email": "nodal-officer@mudrex.example.invalid",
    }
    resp = client.post(
        f"/api/v1/cases/{sample_case.case_id}/notices",
        json=create_payload,
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    notice_id = resp.json()["id"]

    # 1. Download EML
    eml_resp = client.get(
        f"/api/v1/notices/{notice_id}/download-eml",
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert eml_resp.status_code == 200
    assert "message/rfc822" in eml_resp.headers.get("content-type", "")
    assert b"Subject:" in eml_resp.content

    # 2. Download PDF
    pdf_resp = client.get(
        f"/api/v1/notices/{notice_id}/download-pdf",
        headers={"Authorization": f"Bearer {inv_token}"},
    )
    assert pdf_resp.status_code == 200
    assert "application/pdf" in pdf_resp.headers.get("content-type", "")
    assert pdf_resp.content.startswith(b"%PDF"), "Response content must be a valid PDF binary starting with %PDF"
