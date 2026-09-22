"""Unit and integration test suite for Phase 9: Complaint Intake with Guarded Extraction.
Verifies:
1. Deterministic candidate address extraction in English and Hindi complaints.
2. Near-miss format warnings with actionable hints.
3. Substring evidence quote verification rejecting fabricated AI facts.
4. Indian PII masking (Mobile, Aadhaar, PAN, Bank Accounts) under DPDP Act 2023.
5. Provider 'none' operates purely in deterministic mode without external calls.
6. LLM provider error handling and graceful degradation to deterministic mode.
7. REST API endpoints POST /api/v1/intake and POST /api/v1/intake/{id}/create-case with audit logs.

Reference: Phase 9 — Complaint intake with guarded extraction, SIH26183.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, init_db
from app.models import Profile, Case, WalletSubmission, AnalysisRun, ComplaintIntake, AuditLog, generate_uuid
from app.security import create_access_token, hash_password
from app.services.pii_masker import mask_pii
from app.services.complaint_extractor import (
    extract_candidate_identifiers,
    evaluate_identifiers,
    verify_extracted_facts,
    is_substring_contained,
    ComplaintIntakeEngine,
)
from app.llm.schemas import AIExtractionOutput, AmountFact, EntityFact
from app.llm.client import AnthropicClient, OllamaClient, NoneLLMClient


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
def auth_officer(db):
    officer_id = generate_uuid()
    profile = Profile(
        id=officer_id,
        email=f"officer_{officer_id[:8]}@cybercrime.gov.in",
        password_hash=hash_password("OfficerSecure123!"),
        full_name="Inspector Rajesh Kumar",
        role="INVESTIGATOR",
        district="Cyber Crime Cell, New Delhi",
        badge_no="DEL-CYB-8831",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    token = create_access_token(profile.id, profile.email, profile.role)
    return profile, token


@pytest.fixture
def other_officer(db):
    officer_id = generate_uuid()
    profile = Profile(
        id=officer_id,
        email=f"other_{officer_id[:8]}@cybercrime.gov.in",
        password_hash=hash_password("OfficerSecure123!"),
        full_name="Inspector Amit Sharma",
        role="INVESTIGATOR",
        district="Cyber Crime Cell, Mumbai",
        badge_no="MUM-CYB-1042",
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    token = create_access_token(profile.id, profile.email, profile.role)
    return profile, token


# ==============================================================================
# 1. Indian PII Masking Tests (DPDP Act 2023 Compliance)
# ==============================================================================

def test_pii_masking_comprehensive():
    """Verify phone, Aadhaar, PAN, and bank accounts are sanitized while crypto addresses remain intact."""
    sample_text = (
        "Complainant Rajesh Kumar, Mobile: +91 9876543210, Aadhaar: 5432 1098 7654. "
        "My PAN number is ABCDE1234F. I transferred funds from my A/C No: 912345678901 "
        "to fraudster wallet 0x742d35Cc6634C0532925a3b844Bc454e4438f44e on Ethereum."
    )

    masked, redactions = mask_pii(sample_text)

    # 1. PII Redacted
    assert "9876543210" not in masked
    assert "[PHONE_REDACTED]" in masked

    assert "5432 1098 7654" not in masked
    assert "[AADHAAR_REDACTED]" in masked

    assert "ABCDE1234F" not in masked
    assert "[PAN_REDACTED]" in masked

    assert "912345678901" not in masked
    assert "[ACCOUNT_REDACTED]" in masked

    # 2. Crypto address preserved
    assert "0x742d35Cc6634C0532925a3b844Bc454e4438f44e" in masked

    # 3. Redaction count is tracked
    types_redacted = {r["type"] for r in redactions}
    assert "PHONE" in types_redacted
    assert "AADHAAR" in types_redacted
    assert "PAN" in types_redacted
    assert "BANK_ACCOUNT" in types_redacted


def test_pii_masking_hindi_context():
    """Verify bank account keywords in Hindi/Hinglish (khata) are detected and masked."""
    hindi_text = (
        "मेरा खाता नंबर khata: 123456789012 से पैसा कट गया। मेरा मोबाइल नंबर 9811223344 है।"
    )
    masked, redactions = mask_pii(hindi_text)

    assert "123456789012" not in masked
    assert "[ACCOUNT_REDACTED]" in masked
    assert "9811223344" not in masked
    assert "[PHONE_REDACTED]" in masked


# ==============================================================================
# 2. Deterministic Extraction in English & Hindi Text
# ==============================================================================

def test_deterministic_extraction_english():
    """Verify extraction of valid EVM, BTC, and TRON addresses alongside near misses in English text."""
    complaint = (
        "On 14 August 2024, I was lured into an investment scheme on Telegram. "
        "The admin instructed me to send 15,000 USDT to Ethereum address "
        "0x742d35Cc6634C0532925a3b844Bc454e4438f44e. Then I sent 0.5 BTC to "
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa. Later, they gave me another address "
        "0x1234567890abcdef1234567890abcdef1234567 which failed to receive funds."
    )

    candidates = extract_candidate_identifiers(complaint)
    assert len(candidates) >= 3

    accepted, near_misses = evaluate_identifiers(candidates)

    # Valid Ethereum address
    accepted_addrs = [a["address"] for a in accepted]
    assert "0x742d35Cc6634C0532925a3b844Bc454e4438f44e" in accepted_addrs
    assert "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" in accepted_addrs

    eth_entry = next(a for a in accepted if a["address"] == "0x742d35Cc6634C0532925a3b844Bc454e4438f44e")
    assert eth_entry["primary_chain"] == "ETH"
    assert eth_entry["kind"] == "address"

    btc_entry = next(a for a in accepted if a["address"] == "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert btc_entry["primary_chain"] == "BTC"

    # Near miss (39 hex characters instead of 40/42)
    near_tokens = [nm["token"] for nm in near_misses]
    assert "0x1234567890abcdef1234567890abcdef1234567" in near_tokens
    nm_entry = next(nm for nm in near_misses if nm["token"] == "0x1234567890abcdef1234567890abcdef1234567")
    assert "error" in nm_entry
    assert "hint" in nm_entry


def test_deterministic_extraction_hindi():
    """Verify extraction of valid addresses in Hindi text without corruption by Devanagari characters."""
    hindi_complaint = (
        "शिकायतकर्ता का बयान: मुझे टेलीग्राम ग्रुप 'क्रिप्टो वेल्थ क्लब' में जोड़ा गया था। "
        "मुझे कहा गया कि 0x742d35Cc6634C0532925a3b844Bc454e4438f44e पर 50,000 रुपये का यूएसडीटी ट्रांसफर करो। "
        "फिर उन्होंने दूसरा ट्रॉन पता TN3W4H6rK2ce4vX9YnFQHwKENnHjoxb3m9 दिया। "
        "इसके बाद एक अमान्य पता 0xdeadbeefbadaddress1234 दिया।"
    )

    candidates = extract_candidate_identifiers(hindi_complaint)
    accepted, near_misses = evaluate_identifiers(candidates)

    accepted_addrs = [a["address"] for a in accepted]
    assert "0x742d35Cc6634C0532925a3b844Bc454e4438f44e" in accepted_addrs
    assert "TN3W4H6rK2ce4vX9YnFQHwKENnHjoxb3m9" in accepted_addrs

    tron_entry = next(a for a in accepted if a["address"] == "TN3W4H6rK2ce4vX9YnFQHwKENnHjoxb3m9")
    assert tron_entry["primary_chain"] == "TRON"


# ==============================================================================
# 3. Near-Miss Diagnosis & Helpful Hints
# ==============================================================================

def test_near_miss_diagnosis_and_hints():
    """Verify near misses return actionable error messages and hints for typo resolution."""
    # Transposed or invalid base58 checksum
    candidates = [
        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb",  # Invalid BTC checksum
        "0x742d35Cc6634C0532925a3b844Bc454e4438f44",   # 39 chars instead of 40
    ]

    accepted, near_misses = evaluate_identifiers(candidates)
    assert len(accepted) == 0
    assert len(near_misses) == 2

    for nm in near_misses:
        assert nm["error"] is not None and len(nm["error"]) > 0
        assert nm["hint"] is not None and len(nm["hint"]) > 0


# ==============================================================================
# 4. Guarded Fact Extraction & Quote Verification
# ==============================================================================

def test_quote_verification_accepts_valid_and_rejects_fabricated_facts():
    """Verify that every claimed fact must have an exact substring evidence quote in original text."""
    original_text = (
        "On 2024-08-15, victim transferred 2,50,000 INR to suspects through Binance P2P. "
        "The victim was defrauded in an investment scam promising 400% returns."
    )

    # Simulated AI output: 2 authentic facts, 2 fabricated facts
    ai_output = AIExtractionOutput(
        offence_date="2024-08-15",
        offence_date_quote="On 2024-08-15",  # Substring present
        victim_loss_inr=250000.0,
        victim_loss_quote="transferred 2,50,000 INR",  # Substring present
        amounts=[
            AmountFact(
                amount=250000.0,
                currency="INR",
                evidence_quote="2,50,000 INR",  # Substring present
            ),
            AmountFact(
                amount=999999.0,
                currency="USD",
                evidence_quote="lost 999999 USD in Cayman Islands",  # Fabricated! NOT in text
            ),
        ],
        entities_referenced=[
            EntityFact(
                name="Binance",
                category="exchange",
                evidence_quote="through Binance P2P",  # Substring present
            ),
            EntityFact(
                name="Swiss Bank Zurich",
                category="bank",
                evidence_quote="laundered through Swiss Bank Zurich",  # Fabricated!
            ),
        ],
        suggested_typology="investment_scam",
        typology_quote="investment scam promising 400% returns",  # Substring present
        translation_en="Neutral translation",
        summary="Victim reported investment scam fraud.",
    )

    verified_facts, rejected_facts = verify_extracted_facts(ai_output, original_text)

    # 4 verified facts
    v_types = [f["fact_type"] for f in verified_facts]
    assert "offence_date" in v_types
    assert "victim_loss_inr" in v_types
    assert "amount" in v_types
    assert "entity" in v_types
    assert "typology" in v_types

    # 2 rejected facts (fabricated ones)
    assert len(rejected_facts) == 2
    r_reasons = [r["rejection_reason"] for r in rejected_facts]
    assert any("not present in original complaint text" in r for r in r_reasons)


def test_quote_verification_unicode_normalization():
    """Verify NFKC normalization and whitespace flexibility for evidence quotes."""
    original_text = "I  transferred   ₹ 50,000   via  UPI\nto  scammer."
    # Quote with single spaces
    quote = "transferred ₹ 50,000 via UPI"
    assert is_substring_contained(quote, original_text) is True

    # Non-existent quote
    fabricated_quote = "transferred ₹ 50,000 via NetBanking"
    assert is_substring_contained(fabricated_quote, original_text) is False


def test_quote_verification_rejects_invalid_typology_enum():
    """Verify that a typology suggestion not in Phase 8 enum is rejected."""
    original_text = "Victim fell for a romance scam on Tinder."
    ai_output = AIExtractionOutput(
        suggested_typology="romance_scam",  # Not in Phase 8 enum (should map to investment_scam or phishing)
        typology_quote="romance scam",
    )
    verified, rejected = verify_extracted_facts(ai_output, original_text)
    assert len(verified) == 0
    assert len(rejected) == 1
    assert "not a valid Phase 8 typology enum" in rejected[0]["rejection_reason"]


# ==============================================================================
# 5. LLM Provider "none" Mode Tests
# ==============================================================================

def test_provider_none_deterministic_intake():
    """Verify ComplaintIntakeEngine works fully in deterministic mode when provider is none."""
    engine = ComplaintIntakeEngine(provider_override="none")
    complaint = (
        "Victim lost funds on 2024-09-01. Flagged Ethereum address: "
        "0x742d35Cc6634C0532925a3b844Bc454e4438f44e and BTC: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa."
    )

    res = engine.process_complaint(complaint)

    assert res["provider"] == "none"
    assert res["is_deterministic"] is True
    assert "Deterministic Mode" in res["mode_banner"]
    assert len(res["accepted_addresses"]) == 2
    assert "Deterministic intake processed 2 valid crypto identifier" in res["summary"]


# ==============================================================================
# 6. Provider Error Handling & Graceful Degradation
# ==============================================================================

def test_provider_error_graceful_degradation():
    """Verify that if an AI provider errors out, intake falls back cleanly to deterministic mode."""
    with patch.object(AnthropicClient, "_call_api", side_effect=Exception("Anthropic API rate limit 429")):
        engine = ComplaintIntakeEngine(provider_override="anthropic")
        complaint = (
            "Suspect wallet: 0x742d35Cc6634C0532925a3b844Bc454e4438f44e. "
            "Victim phone number: 9876543210."
        )

        res = engine.process_complaint(complaint)

        # Degraded cleanly to deterministic
        assert res["is_deterministic"] is True
        assert res["provider_note"] is not None
        assert "Anthropic error" in res["provider_note"]
        # Address extraction still succeeded deterministically
        assert len(res["accepted_addresses"]) == 1
        assert res["accepted_addresses"][0]["address"] == "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"


# ==============================================================================
# 7. REST API Endpoints & Case Creation Workflow
# ==============================================================================

def test_api_intake_and_create_case_flow(db, auth_officer, other_officer):
    """Verify full end-to-end API lifecycle:
    1. POST /api/v1/intake processes complaint, masks PII, logs audit event.
    2. POST /api/v1/intake/{id}/create-case registers Case and AnalysisRun.
    3. RLS ensures another officer cannot access or create case from first officer's intake.
    """
    officer, token = auth_officer
    other_prof, other_token = other_officer

    complaint_payload = {
        "complaint_text": (
            "I was scammed by a fake broker. My phone is 9876543210. "
            "I transferred crypto to 0x742d35Cc6634C0532925a3b844Bc454e4438f44e. "
            "They also gave me near-miss address 0x1234567890abcdef1234567890abcdef1234567."
        ),
        "language": "en",
    }

    # 1. Process Complaint Intake
    resp = client.post(
        "/api/v1/intake",
        json=complaint_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    intake_id = data["id"]
    assert intake_id is not None
    assert len(data["accepted_addresses"]) == 1
    assert data["accepted_addresses"][0]["address"] == "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    assert len(data["near_misses"]) >= 1
    assert "9876543210" not in data["masked_text"]
    assert "[PHONE_REDACTED]" in data["masked_text"]

    # Check DB record and audit log
    intake_db = db.query(ComplaintIntake).filter(ComplaintIntake.id == intake_id).first()
    assert intake_db is not None
    # Original text stored in DB
    assert "9876543210" in intake_db.original_text

    audit_entry = (
        db.query(AuditLog)
        .filter(AuditLog.target_id == intake_id, AuditLog.action == "COMPLAINT_INTAKE_PROCESSED")
        .first()
    )
    assert audit_entry is not None
    assert audit_entry.officer_id == officer.id

    # 2. RLS Check: Other investigator attempts to create case from officer's intake -> 403 Forbidden
    unauthorized_resp = client.post(
        f"/api/v1/intake/{intake_id}/create-case",
        json={"ncrp_ref": "NCRP/2026/FORBIDDEN"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert unauthorized_resp.status_code == 403

    # 3. Authorized Officer Creates Case
    create_resp = client.post(
        f"/api/v1/intake/{intake_id}/create-case",
        json={
            "ncrp_ref": "NCRP/2026/INTAKE-001",
            "accepted_addresses": ["0x742d35Cc6634C0532925a3b844Bc454e4438f44e"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200, create_resp.text
    case_data = create_resp.json()

    new_case_id = case_data["case_id"]
    assert case_data["ncrp_ref"] == "NCRP/2026/INTAKE-001"
    assert case_data["accepted_addresses_count"] == 1

    # Verify Case and AnalysisRun created in DB
    case_in_db = db.query(Case).filter(Case.case_id == new_case_id).first()
    assert case_in_db is not None
    assert case_in_db.assigned_officer_id == officer.id

    wallet_sub = db.query(WalletSubmission).filter(WalletSubmission.case_id == new_case_id).first()
    assert wallet_sub is not None
    assert wallet_sub.address == "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"

    run = db.query(AnalysisRun).filter(AnalysisRun.submission_id == wallet_sub.submission_id).first()
    assert run is not None
    assert run.status == "PENDING"

    # Verify Case Creation Audit Log
    case_audit = (
        db.query(AuditLog)
        .filter(AuditLog.target_id == new_case_id, AuditLog.action == "CASE_CREATED_FROM_INTAKE")
        .first()
    )
    assert case_audit is not None
    assert case_audit.officer_id == officer.id
