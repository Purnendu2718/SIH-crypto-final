"""Pytest suite for Phase 8 — Multi-Chain Expansion, Bridge Detector, and WebSocket Streaming.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
from app.fixtures.seed_fixtures import seed_vasp_directory
from app.config import settings
from app.services.adapters import get_adapter, EvmAdapter, TronAdapter, FixtureAdapter
from app.services.bridge_detector import detect_bridge_hop, KNOWN_BRIDGE_CONTRACTS

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    seed_vasp_directory()
    yield


def test_evm_adapter_fallback():
    """Verify EvmAdapter smoothly falls back to FixtureAdapter without API keys/RPC."""
    adapter = EvmAdapter(chain="ETH")
    # Scenario 1 suspect address
    txs = adapter.get_transactions("0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A", "ETH")
    assert len(txs) >= 1
    assert txs[0].from_address.lower() == "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A".lower()
    assert txs[0].value == 4.5
    assert txs[0].chain == "ETH"


def test_tron_adapter_fallback():
    """Verify TronAdapter smoothly falls back to FixtureAdapter without TronGrid API keys."""
    adapter = TronAdapter()
    # Scenario 3 TRON address from fixture dataset
    txs = adapter.get_transactions("TR7CrossChainMuleAddressFIXTURE", "TRON")
    assert len(txs) >= 1
    assert txs[0].chain == "TRON"
    assert txs[0].value > 0


def test_chain_adapter_factory():
    """Verify factory routes chains properly under LIVE_MODE toggle."""
    # When LIVE_MODE is False (default air-gapped), returns FixtureAdapter
    settings.LIVE_MODE = False
    assert isinstance(get_adapter("ETH"), FixtureAdapter)

    # When LIVE_MODE is True, returns corresponding live adapters
    settings.LIVE_MODE = True
    try:
        eth_ad = get_adapter("ETH")
        assert isinstance(eth_ad, EvmAdapter)

        poly_ad = get_adapter("POLYGON")
        assert isinstance(poly_ad, EvmAdapter)

        tron_ad = get_adapter("TRON")
        assert isinstance(tron_ad, TronAdapter)

        unk_ad = get_adapter("UNKNOWN_CHAIN")
        assert isinstance(unk_ad, FixtureAdapter)
    finally:
        settings.LIVE_MODE = False


def test_bridge_detector():
    """Verify detection of known cross-chain bridges and decoders."""
    # 1. Arbitrum Gateway
    arb_result = detect_bridge_hop(
        to_address="0x8315177aB297bA92A06054cE80a67Ed4DBd7ed3a",
        from_address="0x1111111111111111111111111111111111111111",
        value=2.5,
    )
    assert arb_result is not None
    assert arb_result.is_bridge is True
    assert arb_result.destination_chain == "ARBITRUM"
    assert "Arbitrum" in arb_result.bridge_name

    # 2. Polygon PoS Bridge
    poly_result = detect_bridge_hop(
        to_address="0xA0c68C638235ee3E043C0350025920ac62847772",
        from_address="0x2222222222222222222222222222222222222222",
        value=1.0,
    )
    assert poly_result is not None
    assert poly_result.destination_chain == "POLYGON"

    # 3. Fixture Scenario 3 Cross-chain placeholder
    fixture_result = detect_bridge_hop(
        to_address="0xBridge_ETH_to_TRON_Placeholder_Contract",
        from_address="0x3333333333333333333333333333333333333333",
        value=5.0,
        metadata={"destination_address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "destination_chain": "TRON"},
    )
    assert fixture_result is not None
    assert fixture_result.destination_chain == "TRON"
    assert fixture_result.recipient == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

    # 4. Normal address (not a bridge)
    normal_result = detect_bridge_hop(
        to_address="0x918F4dE1a980598711E81D3962b9a764d2627E51",
        from_address="0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
    )
    assert normal_result is None


def test_websocket_trace_live_stream():
    """Verify live WebSocket endpoint connects and streams trace hops sequentially."""
    with client.websocket_connect("/api/ws/trace-live") as ws:
        # Send initial inquiry for scenario 1 address
        ws.send_json({
            "address": "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A",
            "chain": "ETH",
        })

        # Receive TRACE_STARTED event
        start_ev = ws.receive_json()
        assert start_ev["type"] == "TRACE_STARTED"
        assert start_ev["chain"] == "ETH"
        assert start_ev["total_hops"] >= 1

        # Receive hop events
        hop_events = []
        while True:
            ev = ws.receive_json()
            if ev["type"] == "HOP_DISCOVERED":
                hop_events.append(ev)
            elif ev["type"] == "TRACE_COMPLETED":
                assert ev["matched_vasp"] == "CoinDCX"
                assert "attribution" in ev
                assert ev["attribution"]["matched_entity"] == "CoinDCX"
                break

        assert len(hop_events) >= 1
        assert hop_events[0]["hop_index"] == 1
