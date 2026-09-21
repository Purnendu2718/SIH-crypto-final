"""Comprehensive Pytest suite for Phase 8B: Scoped Bridge Detector & WebSocket Streaming Graph Animation.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8B.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal, init_db
from app.fixtures.seed_fixtures import seed_vasp_directory
from app.models import Case, WalletSubmission, AnalysisRun, Profile, generate_uuid, utc_now
from app.services.bridge_detector import (
    detect_bridge_hop,
    decode_bridge_receipt_logs,
    KNOWN_BRIDGE_CONTRACTS,
    TOPIC_POLYGON_LOCKED_ERC20,
    TOPIC_ARBITRUM_DEPOSIT,
    TOPIC_ACROSS_FUNDS_DEPOSITED,
    TOPIC_HOP_TRANSFER_SENT,
    TOPIC_PLACEHOLDER_TRANSFER,
)
from app.services.trace_engine import TraceEngine

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Ensure database schema is initialized and Indian VASP directory is seeded."""
    init_db()
    seed_vasp_directory()
    yield


# ==============================================================================
# 1. Scoped Bridge Detector Tests
# ==============================================================================

def test_bridge_detector_named_contracts():
    """Verifies that detect_bridge_hop correctly recognizes explicitly named bridge contracts."""
    # 1. Polygon PoS Bridge
    poly_res = detect_bridge_hop(
        to_address="0xa0c68c638235ee3e043c0350025920ac62847772",
        from_address="0x1111111111111111111111111111111111111111",
        value=5.0,
    )
    assert poly_res is not None
    assert poly_res.is_bridge is True
    assert poly_res.destination_chain == "POLYGON"
    assert "Polygon" in poly_res.bridge_name

    # 2. Arbitrum One Gateway
    arb_res = detect_bridge_hop(
        to_address="0x8315177ab297ba92a06054ce80a67ed4dbd7ed3a",
        from_address="0x1111111111111111111111111111111111111111",
        value=3.5,
    )
    assert arb_res is not None
    assert arb_res.destination_chain == "ARBITRUM"
    assert "Arbitrum" in arb_res.bridge_name

    # 3. Across Protocol
    across_res = detect_bridge_hop(
        to_address="0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5",
        from_address="0x1111111111111111111111111111111111111111",
        value=2.0,
    )
    assert across_res is not None
    assert "Across" in across_res.bridge_name

    # 4. Hop Protocol
    hop_res = detect_bridge_hop(
        to_address="0x3666f603cc164936c1b87e207f36beba4ac5f18a",
        from_address="0x1111111111111111111111111111111111111111",
        value=1.0,
    )
    assert hop_res is not None
    assert "Hop" in hop_res.bridge_name

    # 5. Scenario 3 Fixture Placeholder Bridge
    ph_res = detect_bridge_hop(
        to_address="0xbridge_eth_to_tron_placeholder_contract",
        from_address="0x1111111111111111111111111111111111111111",
        value=4.0,
    )
    assert ph_res is not None
    assert ph_res.destination_chain == "TRON"


def test_bridge_detector_strict_safe_noop_on_unknown_contracts():
    """Confirms the bridge detector strictly no-ops (skips, returns None, never crashes)
    on arbitrary addresses, standard DEX swaps, null values, or unlisted contracts.
    """
    # Random unlisted contract
    assert detect_bridge_hop(to_address="0x1111111111111111111111111111111111111111") is None

    # Uniswap V3 Swap Router (not a cross-chain bridge)
    assert detect_bridge_hop(to_address="0xE592427A0AEce92De3Edee1F18E0157C05861564") is None

    # Empty, None, and garbage inputs must safely return None without throwing
    assert detect_bridge_hop(to_address="") is None
    assert detect_bridge_hop(to_address=None) is None
    assert detect_bridge_hop(to_address="not_an_address_at_all_garbage_string") is None


def test_bridge_detector_receipt_log_decoders():
    """Verifies hand-written receipt log decoders for each bridge protocol."""
    dummy_recipient_topic = "0x000000000000000000000000918f4de1a980598711e81d3962b9a764d2627e51"

    # 1. Polygon log decoding
    poly_logs = [{"topics": [TOPIC_POLYGON_LOCKED_ERC20, "0x0", "0x0", dummy_recipient_topic]}]
    res_poly = decode_bridge_receipt_logs("0xa0c68c638235ee3e043c0350025920ac62847772", poly_logs)
    assert res_poly["destination_chain"] == "POLYGON"
    assert res_poly["recipient"] == "0x918f4de1a980598711e81d3962b9a764d2627e51"
    assert "Polygon" in res_poly["decoding_rule"]

    # 2. Arbitrum log decoding
    arb_logs = [{"topics": [TOPIC_ARBITRUM_DEPOSIT, "0x0", "0x0", dummy_recipient_topic]}]
    res_arb = decode_bridge_receipt_logs("0x8315177ab297ba92a06054ce80a67ed4dbd7ed3a", arb_logs)
    assert res_arb["destination_chain"] == "ARBITRUM"
    assert res_arb["recipient"] == "0x918f4de1a980598711e81d3962b9a764d2627e51"
    assert "Arbitrum" in res_arb["decoding_rule"]

    # 3. Across log decoding
    across_logs = [{"topics": [TOPIC_ACROSS_FUNDS_DEPOSITED, "0x0", "0x0", dummy_recipient_topic]}]
    res_across = decode_bridge_receipt_logs("0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5", across_logs)
    assert res_across["destination_chain"] == "CROSS_CHAIN"
    assert res_across["recipient"] == "0x918f4de1a980598711e81d3962b9a764d2627e51"

    # 4. Unknown logs / unlisted contract returns empty dict safely
    assert decode_bridge_receipt_logs("0x9999999999999999999999999999999999999999", poly_logs) == {}
    assert decode_bridge_receipt_logs("0xa0c68c638235ee3e043c0350025920ac62847772", []) == {}


# ==============================================================================
# 2. WebSocket Trace Streaming Tests
# ==============================================================================

def test_websocket_stream_fixture_scenario_1():
    """Verifies that /api/ws/trace/{submission_id} sequentially streams Scenario 1 hops
    hop-by-hop with proper start and completion frames.
    """
    db = SessionLocal()
    try:
        # Create a test case and submission for Scenario 1
        case_id = generate_uuid()
        sub_id = generate_uuid()
        test_case = Case(
            case_id=case_id,
            ncrp_ref="NCRP-P8B-SC1",
            amount_inr=1125000.0,
            status="OPEN",
            created_at=utc_now(),
        )
        sub = WalletSubmission(
            submission_id=sub_id,
            case_id=case_id,
            address="0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
            chain="ETH",
            submitted_at=utc_now(),
        )
        db.add(test_case)
        db.add(sub)
        db.commit()

        # Run trace engine to persist paths
        run_id = generate_uuid()
        test_run = AnalysisRun(
            run_id=run_id,
            submission_id=sub_id,
            status="COMPLETED",
            started_at=utc_now(),
        )
        db.add(test_run)
        db.commit()

        engine = TraceEngine()
        engine.execute_trace(sub.address, sub.chain, run_id=run_id, db=db)
    finally:
        db.close()

    # Connect to WebSocket
    with client.websocket_connect(f"/api/ws/trace/{sub_id}") as ws:
        # 1. TRACE_STARTED event
        start_msg = ws.receive_json()
        assert start_msg["type"] == "TRACE_STARTED"
        assert start_msg["submission_id"] == sub_id
        assert start_msg["start_address"] == "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
        assert start_msg["total_hops"] >= 2

        # 2. HOP_DISCOVERED events
        hop1 = ws.receive_json()
        assert hop1["type"] == "HOP_DISCOVERED"
        assert hop1["hop_index"] == 1
        assert hop1["from_addr"].lower() == "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A".lower()
        assert hop1["value"] == 4.5
        assert hop1["is_bridge"] is False

        hop2 = ws.receive_json()
        assert hop2["type"] == "HOP_DISCOVERED"
        assert hop2["hop_index"] == 2
        assert "CoinDCX" in hop2["to_addr"]
        assert hop2["value"] == 4.498

        # 3. TRACE_COMPLETED event
        complete_msg = ws.receive_json()
        assert complete_msg["type"] == "TRACE_COMPLETED"
        assert complete_msg["matched_vasp"] == "CoinDCX"


def test_websocket_stream_scenario_3_crosschain_bridge_hop():
    """Verifies that Scenario 3 WebSocket stream detects and emits cross-chain bridge
    metadata for the bridge contract hop.
    """
    db = SessionLocal()
    try:
        case_id = generate_uuid()
        sub_id = generate_uuid()
        test_case = Case(
            case_id=case_id,
            ncrp_ref="NCRP-P8B-SC3",
            amount_inr=750000.0,
            status="OPEN",
            created_at=utc_now(),
        )
        sub = WalletSubmission(
            submission_id=sub_id,
            case_id=case_id,
            address="0x892a0194856cD192801F6281983017A8128919a0",
            chain="ETH",
            submitted_at=utc_now(),
        )
        db.add(test_case)
        db.add(sub)
        db.commit()

        run_id = generate_uuid()
        test_run = AnalysisRun(
            run_id=run_id,
            submission_id=sub_id,
            status="COMPLETED",
            started_at=utc_now(),
        )
        db.add(test_run)
        db.commit()

        engine = TraceEngine()
        engine.execute_trace(sub.address, sub.chain, run_id=run_id, db=db)
    finally:
        db.close()

    with client.websocket_connect(f"/api/ws/trace/{sub_id}") as ws:
        start_msg = ws.receive_json()
        assert start_msg["type"] == "TRACE_STARTED"

        # Hop 1: suspect -> bridge placeholder
        hop1 = ws.receive_json()
        assert hop1["type"] == "HOP_DISCOVERED"
        assert hop1["is_bridge"] is True
        assert hop1["bridge_details"] is not None
        assert hop1["bridge_details"]["destination_chain"] == "TRON"


def test_websocket_stream_case_id_and_run_id_resolution():
    """Verifies that /api/ws/trace/{identifier} flexibly resolves case_id or run_id."""
    db = SessionLocal()
    try:
        case_id = generate_uuid()
        sub_id = generate_uuid()
        test_case = Case(
            case_id=case_id,
            ncrp_ref="NCRP-P8B-CASE-LOOKUP",
            amount_inr=500000.0,
            status="OPEN",
            created_at=utc_now(),
        )
        sub = WalletSubmission(
            submission_id=sub_id,
            case_id=case_id,
            address="0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
            chain="ETH",
            submitted_at=utc_now(),
        )
        db.add(test_case)
        db.add(sub)
        db.commit()

        run_id = generate_uuid()
        test_run = AnalysisRun(
            run_id=run_id,
            submission_id=sub_id,
            status="COMPLETED",
            started_at=utc_now(),
        )
        db.add(test_run)
        db.commit()

        engine = TraceEngine()
        res = engine.execute_trace(sub.address, sub.chain, run_id=run_id, db=db)
        run_id = res.run_id
    finally:
        db.close()

    # 1. Connect using case_id
    with client.websocket_connect(f"/api/ws/trace/{case_id}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "TRACE_STARTED"

    # 2. Connect using run_id
    with client.websocket_connect(f"/api/ws/trace/{run_id}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "TRACE_STARTED"


def test_websocket_stream_live_mode_query():
    """Verifies /api/ws/trace-live with LIVE_MODE=True streams confirmations and freshness metrics."""
    settings.LIVE_MODE = True
    try:
        with client.websocket_connect("/api/ws/trace-live") as ws:
            ws.send_json({
                "address": "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
                "chain": "ETH",
            })

            start_msg = ws.receive_json()
            assert start_msg["type"] == "TRACE_STARTED"
            assert start_msg["chain"] == "ETH"

            hop1 = ws.receive_json()
            assert hop1["type"] == "HOP_DISCOVERED"
            assert "confirmations" in hop1
            assert "low_confirmation" in hop1
            assert "is_pending" in hop1

            hop2 = ws.receive_json()
            assert hop2["type"] == "HOP_DISCOVERED"

            comp = ws.receive_json()
            assert comp["type"] == "TRACE_COMPLETED"
            assert comp["matched_vasp"] == "CoinDCX"
    finally:
        settings.LIVE_MODE = False
