"""Isolated Test Suite for Phase 8: Real-Time Live Search & Live Chain Adapters.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8.
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.services.adapters import (
    get_adapter,
    FixtureAdapter,
    EvmAdapter,
    TronAdapter,
    BtcAdapter,
)
from app.services.adapters.cache import adapter_cache, AdapterCache
from app.services.adapters.base import NormalizedTransaction
from app.security import create_access_token


@pytest.fixture
def auth_header():
    """Generates an authorization bearer token for a test investigator officer."""
    from app.database import SessionLocal
    from app.models import Profile, generate_uuid

    db = SessionLocal()
    try:
        officer = db.query(Profile).filter(Profile.email == "patel@sentinel.gov.in").first()
        if not officer:
            officer = Profile(
                id=generate_uuid(),
                email="patel@sentinel.gov.in",
                full_name="Inspector Patel",
                badge_no="DL-8802",
                role="INVESTIGATOR",
                district="Delhi Central",
            )
            db.add(officer)
            db.commit()
            db.refresh(officer)
        officer_id = officer.id
    finally:
        db.close()

    token = create_access_token(
        officer_id=officer_id,
        email="patel@sentinel.gov.in",
        role="INVESTIGATOR",
    )
    return {"Authorization": f"Bearer {token}"}


def test_mode_toggle_airgapped_default():
    """Confirms that with LIVE_MODE=False (default), get_adapter exclusively returns
    FixtureAdapter for all chains, guaranteeing 100% offline air-gapped execution with zero network requests.
    """
    settings.LIVE_MODE = False

    adapter_eth = get_adapter("ETH")
    adapter_tron = get_adapter("TRON")
    adapter_btc = get_adapter("BTC")

    assert isinstance(adapter_eth, FixtureAdapter)
    assert isinstance(adapter_tron, FixtureAdapter)
    assert isinstance(adapter_btc, FixtureAdapter)


def test_mode_toggle_live_mode_activation():
    """Confirms that with LIVE_MODE=True, get_adapter routes to the appropriate
    live network adapters for EVM, TRON, and BTC.
    """
    settings.LIVE_MODE = True
    try:
        adapter_eth = get_adapter("ETH")
        adapter_tron = get_adapter("TRON")
        adapter_btc = get_adapter("BTC")

        assert isinstance(adapter_eth, EvmAdapter)
        assert isinstance(adapter_tron, TronAdapter)
        assert isinstance(adapter_btc, BtcAdapter)
    finally:
        settings.LIVE_MODE = False


def test_evm_adapter_confirmation_freshness_and_reorg_warning():
    """Tests EvmAdapter direct RPC parsing, confirmation calculation,
    and flagging of low-confirmation (< 3) transactions subject to reorg.
    """
    adapter = EvmAdapter(rpc_url="https://mock-evm-node.local")

    # Mock JSON-RPC: block 100, current block 101 -> 2 confirmations (< 3 threshold)
    with patch.object(adapter, "_rpc_call") as mock_rpc:
        def rpc_side_effect(method, params):
            if method == "eth_getTransactionByHash":
                return {
                    "hash": "0x4b72898c1143a443a290bf4255169a9d20c5d6bc9f000d603a7ef45e7f123456",
                    "from": "0x71C8A188c03565257B43997A522e84120359f131",
                    "to": "0x000000000000000000000000000000000000dead",
                    "value": hex(int(1.5 * 1e18)),
                    "blockNumber": hex(100),
                }
            elif method == "eth_blockNumber":
                return hex(101)  # latest block 101 -> 101 - 100 + 1 = 2 confirmations
            elif method == "eth_getTransactionReceipt":
                return {"gasUsed": "0x5208"}
            return None

        mock_rpc.side_effect = rpc_side_effect

        tx = adapter.get_transaction_by_hash(
            "0x4b72898c1143a443a290bf4255169a9d20c5d6bc9f000d603a7ef45e7f123456"
        )

        assert tx is not None
        assert tx.from_address.lower() == "0x71C8A188c03565257B43997A522e84120359f131".lower()
        assert tx.value == 1.5
        assert tx.confirmations == 2
        assert tx.low_confirmation is True  # 2 < 3 confirmations -> must be flagged as low confirmation!
        assert tx.is_pending is False


def test_evm_adapter_pending_mempool_transaction():
    """Tests EvmAdapter handling of pending transactions (blockNumber is None)."""
    adapter = EvmAdapter(rpc_url="https://mock-evm-node.local")

    with patch.object(adapter, "_rpc_call") as mock_rpc:
        mock_rpc.return_value = {
            "hash": "0x9999999c1143a443a290bf4255169a9d20c5d6bc9f000d603a7ef45e7f999999",
            "from": "0x71C8A188c03565257B43997A522e84120359f131",
            "to": "0x000000000000000000000000000000000000dead",
            "value": "0x0",
            "blockNumber": None,  # Pending in mempool
        }

        tx = adapter.get_transaction_by_hash(
            "0x9999999c1143a443a290bf4255169a9d20c5d6bc9f000d603a7ef45e7f999999"
        )

        assert tx is not None
        assert tx.is_pending is True
        assert tx.confirmations == 0
        assert tx.low_confirmation is True


def test_btc_adapter_unconfirmed_mempool_space_detection():
    """Tests BtcAdapter mempool.space API parsing, surfacing unconfirmed mempool
    transactions immediately with confirmations=0 and low_confirmation=True.
    """
    adapter = BtcAdapter()

    fake_mempool_resp = {
        "txid": "f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16",
        "vin": [
            {
                "prevout": {
                    "scriptpubkey_address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
                    "value": 50000000,
                }
            }
        ],
        "vout": [
            {
                "scriptpubkey_address": "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
                "value": 45000000,
            }
        ],
        "status": {
            "confirmed": False,  # unconfirmed in mempool
            "block_height": None,
        },
    }

    with patch("httpx.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = fake_mempool_resp
        mock_get.return_value = mock_response

        tx = adapter.get_transaction_by_hash(fake_mempool_resp["txid"])

        assert tx is not None
        assert tx.tx_hash == fake_mempool_resp["txid"]
        assert tx.from_address == "1BoatSLRHtKNngkdXEeobR76b53LETtpyT"
        assert tx.to_address == "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo"
        assert tx.value == 0.45  # 45000000 sats / 1e8 = 0.45 BTC
        assert tx.confirmations == 0
        assert tx.is_pending is True
        assert tx.low_confirmation is True


def test_short_ttl_cache_stale_fallback_on_rate_limit():
    """Tests the in-memory cache resilience: when a live call fails or hits HTTP 429 rate limit,
    the cache serves the previous entry marked is_stale=True rather than crashing.
    """
    adapter_cache.clear()
    adapter = EvmAdapter(rpc_url="https://mock-evm-node.local")

    cached_tx = NormalizedTransaction(
        tx_hash="0x5555555c1143a443a290bf4255169a9d20c5d6bc9f000d603a7ef45e7f555555",
        chain="ETH",
        from_address="0x71C8A188c03565257B43997A522e84120359f131",
        to_address="0x28C6c06298d514Db089934071355E5743bf21d60",
        value=2.0,
        timestamp=datetime.now(timezone.utc),
        confirmations=1,
        low_confirmation=True,
    )

    # Seed the cache and simulate expiration to verify stale fallback
    cache_key = f"evm:tx:{cached_tx.tx_hash.lower()}"
    adapter_cache.set(cache_key, cached_tx, has_low_confirmation=True)
    adapter_cache._store[cache_key].created_at -= 1000

    # Simulate live node returning an error (e.g. rate limit HTTP 429)
    with patch.object(adapter, "_rpc_call", return_value=None):
        tx = adapter.get_transaction_by_hash(cached_tx.tx_hash)

        assert tx is not None
        assert tx.tx_hash == cached_tx.tx_hash
        assert tx.is_stale is True  # Stale data served gracefully


def test_unified_search_endpoint_with_live_tx_hash(auth_header):
    """Tests POST /api/v1/search resolving an EVM transaction hash, creating the case,
    and returning confirmation and reorg warning metrics.
    """
    client = TestClient(app)

    # Search scenario 1 tx hash present in fixture dataset
    sample_tx_hash = "0xaaa1110000000000000000000000000000000000000000000000000000000001"

    response = client.post(
        "/api/v1/search",
        json={"query": sample_tx_hash, "amount_inr": 500000.0},
        headers=auth_header,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == sample_tx_hash
    assert data["query_type"] == "TRANSACTION_HASH"
    assert data["detected_chain"] == "ETH"
    assert data["resolved_address"] == "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    assert data["case_id"] is not None
    assert data["status"] in ("ANALYSIS_COMPLETE_ATTRIBUTED", "COMPLETED")
    assert data["matched_entity"] == "CoinDCX"
    assert "confirmations" in data
    assert "low_confirmation" in data
