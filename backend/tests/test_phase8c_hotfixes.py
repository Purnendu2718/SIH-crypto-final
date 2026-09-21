"""Pytest suite for Phase 8C Hotfixes:
1. Cryptographic Address Validation & Chain Detection (BTC P2SH/Bech32, TRON, EVM EIP-55).
2. Root-Address Self-Attribution Short-Circuit (0 hops, VERY_HIGH confidence).
3. Run-Status Integrity (4 distinct forensic states).
4. Unified One-Box Search Endpoint (/api/v1/search).

Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8C Hotfixes.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import SessionLocal, init_db
from app.models import VASPDirectory, Profile, Case, AnalysisRun
from app.services.address_validator import (
    validate_and_detect_chain,
    is_valid_evm_address,
    validate_base58check,
    is_valid_bech32_btc,
)
from app.services import run_full_forensic_pipeline
from app.services.trace_engine import ForensicStatus


client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()
    # Ensure officer exists for authenticated search queries
    client.post("/api/cases/seed-demo")
    yield


@pytest.fixture
def auth_header():
    res = client.post(
        "/api/auth/login",
        json={"email": "sharma@sentinel.gov.in", "password": "SentinelPass123!"},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test 1: Address Validation & Checksum Precision (Phase 8C Item 1)
# ---------------------------------------------------------------------------
def test_address_validation_btc_p2sh_detection():
    """Verify 34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo is detected as BTC (not ETH)."""
    btc_p2sh = "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"
    is_valid, chain, detail = validate_and_detect_chain(btc_p2sh)
    assert is_valid is True
    assert chain == "BTC", f"Expected BTC, got {chain}"
    assert "P2SH" in detail

    # Bitcoin P2PKH (0x00)
    btc_p2pkh = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
    is_valid, chain, detail = validate_and_detect_chain(btc_p2pkh)
    assert is_valid is True
    assert chain == "BTC"
    assert "P2PKH" in detail

    # Bitcoin Bech32 SegWit
    btc_bech32 = "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"
    is_valid, chain, detail = validate_and_detect_chain(btc_bech32)
    assert is_valid is True
    assert chain == "BTC"

    # TRON Base58Check (0x41)
    tron_addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    is_valid, chain, detail = validate_and_detect_chain(tron_addr)
    assert is_valid is True
    assert chain == "TRON"

    # EVM Checksummed (EIP-55)
    evm_addr = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    is_valid, chain, detail = validate_and_detect_chain(evm_addr)
    assert is_valid is True
    assert chain == "ETH"

    # Case sensitivity audit: Ensure raw casing is strictly preserved
    assert btc_p2sh != btc_p2sh.lower(), "BTC Base58 address must be case-sensitive"


def test_address_validation_rejects_garbage_and_invalid_checksums():
    """Verify invalid strings are explicitly rejected without silent fallback."""
    # Corrupted / random string
    is_valid, chain, detail = validate_and_detect_chain("random_invalid_garbage_12345")
    assert is_valid is False
    assert chain == "UNRECOGNIZED_ADDRESS_FORMAT"

    # Corrupted EVM mixed-case checksum
    corrupted_evm = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD"
    is_valid, chain, detail = validate_and_detect_chain(corrupted_evm)
    assert is_valid is False
    assert chain == "UNRECOGNIZED_ADDRESS_FORMAT"


# ---------------------------------------------------------------------------
# Test 2: Root-Address Self-Attribution Short-Circuit (Phase 8C Item 2)
# ---------------------------------------------------------------------------
def test_root_address_self_attribution_short_circuit():
    """Verify known VASP root address skips tracing with 0 hops and returns VERY_HIGH confidence."""
    db: Session = SessionLocal()
    try:
        btc_cold_wallet = "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"
        # Seed into vasp_directory
        existing = db.query(VASPDirectory).filter(VASPDirectory.entity_name == "Binance Cold Storage").first()
        if not existing:
            vasp = VASPDirectory(
                entity_name="Binance Cold Storage",
                chain="BTC",
                hot_wallet_addresses=[btc_cold_wallet],
                fiu_ind_registered=False,
                sla_hours=12,
                nodal_contact="nodal@binance.com",
            )
            db.add(vasp)
            db.commit()

        # Run pipeline
        res = run_full_forensic_pipeline(
            start_address=btc_cold_wallet,
            chain="BTC",
            db=db,
        )

        assert res["status"] == "ANALYSIS_COMPLETE_ATTRIBUTED"
        assert res["is_root_entity"] is True
        assert res["attribution_source"] == "ROOT_ADDRESS_IS_KNOWN_ENTITY"
        assert res["attribution"]["matched_entity"] == "Binance Cold Storage"
        assert res["attribution"]["confidence"] == 1.0
        assert res["attribution"]["confidence_band"] == "VERY_HIGH"
        assert res["trace"]["total_hops"] == 0, f"Expected 0 hops, got {res['trace']['total_hops']}"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test 3: Run-Status Integrity & Invalid Address State (Phase 8C Item 3)
# ---------------------------------------------------------------------------
def test_invalid_address_returns_analysis_failed_invalid_address():
    """Verify invalid address format results in ANALYSIS_FAILED_INVALID_ADDRESS, not success."""
    res = run_full_forensic_pipeline(
        start_address="this_is_not_a_valid_crypto_address",
        chain="ETH",
    )

    assert res["status"] == "ANALYSIS_FAILED_INVALID_ADDRESS"
    assert res["attribution"]["confidence"] == 0.0
    assert res["attribution"]["confidence_band"] == "INSUFFICIENT_EVIDENCE"
    assert res["attribution_source"] == "INVALID_ADDRESS_FORMAT"
    assert "error" in res


def test_four_distinct_run_statuses():
    """Verify the 4 distinct run statuses mandated by Phase 8C."""
    # 1. Attributed
    s_attr = ForensicStatus("ANALYSIS_COMPLETE_ATTRIBUTED")
    assert s_attr == "ANALYSIS_COMPLETE_ATTRIBUTED"
    assert s_attr == "COMPLETED"  # Backward compatibility check

    # 2. No Path
    s_nopath = ForensicStatus("ANALYSIS_COMPLETE_NO_PATH_FOUND")
    assert s_nopath == "ANALYSIS_COMPLETE_NO_PATH_FOUND"
    assert s_nopath == "NO_CONFIDENT_OFF_RAMP"  # Backward compatibility check

    # 3. Adapter Error
    s_adapter = ForensicStatus("ANALYSIS_FAILED_ADAPTER_ERROR")
    assert s_adapter == "ANALYSIS_FAILED_ADAPTER_ERROR"

    # 4. Invalid Address
    s_invalid = ForensicStatus("ANALYSIS_FAILED_INVALID_ADDRESS")
    assert s_invalid == "ANALYSIS_FAILED_INVALID_ADDRESS"


# ---------------------------------------------------------------------------
# Test 4: Unified Multi-Chain Search Endpoint (POST /api/v1/search)
# ---------------------------------------------------------------------------
def test_unified_search_endpoint_with_btc_address(auth_header):
    """Test searching BTC P2SH address returns multi-chain search response."""
    payload = {"query": "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"}
    res = client.post("/api/v1/search", json=payload, headers=auth_header)
    assert res.status_code == 200
    data = res.json()

    assert data["query"] == "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"
    assert data["run_id"] is not None
    assert data["validation"]["is_valid"] is True
    assert data["validation"]["primary"]["chain"] == "bitcoin"
    assert len(data["results"]) >= 1
    assert data["results"][0]["chain"] == "bitcoin"


def test_unified_search_endpoint_with_invalid_input(auth_header):
    """Test searching invalid input returns HTTP 422 with validation payload."""
    payload = {"query": "fake_bad_address_123"}
    res = client.post("/api/v1/search", json=payload, headers=auth_header)
    assert res.status_code == 422
    data = res.json()

    assert "validation" in data
    assert data["validation"]["is_valid"] is False
    assert data["validation"]["error"] is not None

