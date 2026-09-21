"""Pytest suite for Phase 3 Trace Engine.
Verifies bounded BFS, dust filtering, hop budget limits, and scenario convergence.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import pytest
from app.database import SessionLocal, init_db
from app.models import AnalysisRun, TracePath, WalletSubmission, Case, Profile, generate_uuid
from app.services.trace_engine import TraceEngine, trace_wallet_submission


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    yield


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_scenario_1_reaches_labeled_exchange_within_2_to_3_hops(db_session):
    """Scenario 1: Suspect address reaches CoinDCX within 2-3 hops."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    engine = TraceEngine(max_hops=15, dust_threshold=0.001)

    result = engine.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db_session)

    assert result.status == "COMPLETED"
    assert 2 <= result.total_hops <= 3, f"Expected 2-3 hops, got {result.total_hops}"
    assert result.matched_entity == "CoinDCX"
    assert result.matched_hot_wallet.lower() == "0xCoinDCX_HotWallet_ETH_FIXTURE_1".lower()
    assert len(result.paths) == 2


def test_scenario_2_reaches_wazirx_after_mixer(db_session):
    """Scenario 2: Suspect address routes through privacy mixer and converges at WazirX."""
    suspect_addr = "0x3a9F784260D672b15Fa0e20f18837138096c7B22"
    engine = TraceEngine(max_hops=15, dust_threshold=0.001)

    result = engine.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db_session)

    assert result.status == "COMPLETED"
    assert result.matched_entity == "WazirX"
    assert result.total_hops == 5
    assert result.matched_hot_wallet.lower() == "0xWazirX_HotWallet_ETH_FIXTURE_1".lower()


def test_scenario_3_reaches_zebpay_via_crosschain_bridge(db_session):
    """Scenario 3: Suspect address bridges from ETH to TRON and reaches ZebPay."""
    suspect_addr = "0x892a0194856cD192801F6281983017A8128919a0"
    engine = TraceEngine(max_hops=15, dust_threshold=0.001)

    result = engine.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db_session)

    assert result.status == "COMPLETED"
    assert result.matched_entity == "ZebPay"
    assert result.total_hops == 3
    assert result.matched_hot_wallet.lower() == "TR7ZebPay_HotWallet_TRX_FIXTURE_1".lower()


def test_scenario_4_terminates_with_no_confident_off_ramp(db_session):
    """Scenario 4: Long 8-hop path without a known VASP hot wallet must return NO_CONFIDENT_OFF_RAMP."""
    suspect_addr = "0x992dE819385610293751a09281754910284759A1"
    engine = TraceEngine(max_hops=15, dust_threshold=0.001)

    result = engine.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db_session)

    # Must NOT fabricate a destination
    assert result.status == "NO_CONFIDENT_OFF_RAMP", f"Expected NO_CONFIDENT_OFF_RAMP, got {result.status}"
    assert result.matched_entity is None
    assert result.matched_hot_wallet is None
    assert result.total_hops == 8


def test_no_scenario_throws(db_session):
    """Assert all 4 scenario addresses run without throwing exceptions."""
    scenario_addrs = [
        ("0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A", "ETH"),
        ("0x3a9F784260D672b15Fa0e20f18837138096c7B22", "ETH"),
        ("0x892a0194856cD192801F6281983017A8128919a0", "ETH"),
        ("0x992dE819385610293751a09281754910284759A1", "ETH"),
        ("0xNonExistentWalletAddress0000000000000000", "ETH"),
    ]
    engine = TraceEngine(max_hops=15)

    for addr, chain in scenario_addrs:
        res = engine.execute_trace(start_address=addr, initial_chain=chain, db=db_session)
        assert res is not None
        assert res.status in ["COMPLETED", "NO_CONFIDENT_OFF_RAMP"]


def test_hop_budget_exhaustion_does_not_fabricate(db_session):
    """Assert when hop budget is exhausted early, run is marked NO_CONFIDENT_OFF_RAMP."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    # Set max_hops = 1, so it cannot reach the 2nd hop hot wallet
    constrained_engine = TraceEngine(max_hops=1)

    result = constrained_engine.execute_trace(start_address=suspect_addr, initial_chain="ETH", db=db_session)

    assert result.total_hops == 1
    assert result.status == "NO_CONFIDENT_OFF_RAMP"
    assert result.matched_entity is None


def test_trace_wallet_submission_persists_to_db(db_session):
    """Test trace_wallet_submission integrates with Case and AnalysisRun models."""
    # Create test case and submission
    c = Case(case_id=generate_uuid(), ncrp_ref=f"NCRP/2026/TEST-TRACE-{generate_uuid()[:4]}")
    db_session.add(c)
    db_session.flush()

    sub = WalletSubmission(
        submission_id=generate_uuid(),
        case_id=c.case_id,
        chain="ETH",
        address="0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
    )
    db_session.add(sub)
    db_session.commit()

    # Execute trace via helper
    trace_res = trace_wallet_submission(submission_id=sub.submission_id, db=db_session)

    assert trace_res.status == "COMPLETED"
    assert trace_res.matched_entity == "CoinDCX"

    # Verify rows in database
    db_paths = db_session.query(TracePath).filter(TracePath.run_id == trace_res.run_id).all()
    assert len(db_paths) == 2

    db_run = db_session.query(AnalysisRun).filter(AnalysisRun.run_id == trace_res.run_id).first()
    assert db_run.status == "COMPLETED"
    assert db_run.completed_at is not None
