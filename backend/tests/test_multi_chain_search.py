"""Unit and integration tests for Multi-Chain Forensics Search & Adapters with respx.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import pytest
import respx
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services.providers.bitcoin import BitcoinAdapter
from app.services.providers.tron import TronProviderAdapter
from app.services.providers.solana import SolanaAdapter
from app.services.providers.xrp import XrpAdapter
from app.services.providers.stellar import StellarAdapter
from app.services.providers.evm import EvmProviderAdapter
from app.services.providers.blockchair import BlockchairAdapter
from app.services.providers.cardano import CardanoAdapter

client = TestClient(app)

GENESIS_ADDR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
CORRUPTED_GENESIS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb"
ENS_NAME = "vitalik.eth"
TX_HASH_64 = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
MONERO_ADDR = "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A"


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------

@respx.mock
def test_search_genesis_address_returns_bitcoin_and_satoshi_label():
    """Verify genesis address returns HTTP 200, primary chain bitcoin, and Satoshi label."""
    # Mock mempool.space Esplora responses
    respx.get(f"https://mempool.space/api/address/{GENESIS_ADDR}").mock(
        return_value=httpx.Response(
            200,
            json={
                "chain_stats": {
                    "funded_txo_sum": 5000000000,
                    "spent_txo_sum": 0,
                    "tx_count": 1,
                },
                "mempool_stats": {
                    "funded_txo_sum": 0,
                    "spent_txo_sum": 0,
                    "tx_count": 0,
                },
            },
        )
    )
    respx.get(f"https://mempool.space/api/address/{GENESIS_ADDR}/txs").mock(
        return_value=httpx.Response(200, json=[])
    )

    res = client.post("/api/v1/search", json={"query": GENESIS_ADDR})
    assert res.status_code == 200
    data = res.json()

    assert data["query"] == GENESIS_ADDR
    assert data["validation"]["is_valid"] is True
    assert data["validation"]["primary"]["chain"] == "bitcoin"
    assert data["validation"]["certainty"] == "verified"

    results = data["results"]
    assert len(results) >= 1
    btc_res = results[0]
    assert btc_res["chain"] == "bitcoin"
    assert btc_res["status"] == "ok"
    assert btc_res["summary"]["balance"] == 50.0
    assert btc_res["source"] == "mempool.space"

    # Known entities label check: Satoshi Nakamoto
    labels = btc_res["labels"]
    assert any("Satoshi Nakamoto" in l["label"] for l in labels)


def test_search_corrupted_genesis_address_returns_422():
    """One-character corrupted checksummed address returns HTTP 422 with error."""
    res = client.post("/api/v1/search", json={"query": CORRUPTED_GENESIS})
    assert res.status_code == 422
    data = res.json()
    assert "validation" in data
    val = data["validation"]
    assert val["is_valid"] is False
    assert val["error"] is not None
    assert "checksum" in val["error"].lower()


def test_search_corrupted_evm_returns_422_with_hint():
    """Corrupted EVM mixed-case address returns HTTP 422 with error and hint."""
    corrupted_evm = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAeD"
    res = client.post("/api/v1/search", json={"query": corrupted_evm})
    assert res.status_code == 422
    data = res.json()
    assert "validation" in data
    val = data["validation"]
    assert val["is_valid"] is False
    assert val["error"] is not None
    assert val["hint"] is not None



def test_search_ens_name_returns_needs_resolution():
    """ENS name returns status needs_resolution without guessing an address."""
    res = client.post("/api/v1/search", json={"query": ENS_NAME})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "needs_resolution"
    assert data["validation"]["kind"] == "ens_name"



@respx.mock
def test_search_64_hex_transaction_hash():
    """64-hex string is recognized as transaction_hash and probed."""
    respx.get(f"https://mempool.space/api/tx/{TX_HASH_64}").mock(
        return_value=httpx.Response(
            200,
            json={
                "txid": TX_HASH_64,
                "fee": 0,
                "status": {"confirmed": True, "block_height": 0},
                "vout": [],
            },
        )
    )

    res = client.post("/api/v1/search", json={"query": TX_HASH_64})
    assert res.status_code == 200
    data = res.json()
    assert data["validation"]["kind"] == "transaction_hash"
    assert data["validation"]["is_valid"] is True
    assert len(data["results"]) >= 1


def test_search_monero_address_returns_not_applicable():
    """Monero address returns status not_applicable with privacy chain note."""
    res = client.post("/api/v1/search", json={"query": MONERO_ADDR})
    assert res.status_code == 200
    data = res.json()
    assert data["validation"]["is_valid"] is True
    results = data["results"]
    assert len(results) >= 1
    xmr_res = results[0]
    assert xmr_res["chain"] == "monero"
    assert xmr_res["status"] == "not_applicable"
    assert "privacy chain" in xmr_res["summary"]["note"].lower()


# ---------------------------------------------------------------------------
# Individual Adapter Unit Tests with recorded/mocked responses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@respx.mock
async def test_tron_adapter_mocked():
    adapter = TronProviderAdapter()
    addr = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    respx.get(f"https://api.trongrid.io/v1/accounts/{addr}").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"balance": 1500000000, "latest_opration_time": 1700000000000}]},
        )
    )
    respx.get(f"https://api.trongrid.io/v1/accounts/{addr}/transactions?limit=20").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    out = await adapter.lookup_address(addr)
    assert out["status"] == "ok"
    assert out["chain"] == "tron"
    assert out["summary"]["balance"] == 1500.0


@pytest.mark.asyncio
@respx.mock
async def test_solana_adapter_mocked():
    adapter = SolanaAdapter()
    addr = "11111111111111111111111111111111"
    respx.post("https://api.mainnet-beta.solana.com").mock(
        return_value=httpx.Response(
            200,
            json={"jsonrpc": "2.0", "result": {"value": {"lamports": 2500000000, "owner": "1111"}}},
        )
    )

    out = await adapter.lookup_address(addr)
    assert out["status"] == "ok"
    assert out["chain"] == "solana"
    assert out["summary"]["balance"] == 2.5


@pytest.mark.asyncio
@respx.mock
async def test_xrpl_adapter_act_not_found():
    adapter = XrpAdapter()
    addr = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"
    respx.post("https://xrplcluster.com").mock(
        return_value=httpx.Response(
            200,
            json={"result": {"error": "actNotFound"}},
        )
    )

    out = await adapter.lookup_address(addr)
    assert out["status"] == "not_found"
    assert out["chain"] == "xrp_ledger"


@pytest.mark.asyncio
@respx.mock
async def test_stellar_adapter_mocked():
    adapter = StellarAdapter()
    addr = "GAAZI4TCR3TY5OJHCTJC2A4QSY6CJWJH5IAJTGKIN2ER7LBNVKOCCWN7"
    respx.get(f"https://horizon.stellar.org/accounts/{addr}").mock(
        return_value=httpx.Response(
            200,
            json={"balances": [{"asset_type": "native", "balance": "100.5"}], "sequence": "123"},
        )
    )
    respx.get(f"https://horizon.stellar.org/accounts/{addr}/transactions?order=desc&limit=20").mock(
        return_value=httpx.Response(200, json={"_embedded": {"records": []}})
    )

    out = await adapter.lookup_address(addr)
    assert out["status"] == "ok"
    assert out["summary"]["balance"] == 100.5


@pytest.mark.asyncio
@respx.mock
async def test_evm_adapter_mocked():
    adapter = EvmProviderAdapter(chain_key="ethereum")
    addr = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    # eth_getBalance
    respx.post("https://ethereum-rpc.publicnode.com").mock(
        side_effect=[
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "0xde0b6b3a7640000"}), # 1 ETH
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "result": "0x5"}), # Nonce 5
            httpx.Response(200, json={"jsonrpc": "2.0", "id": 3, "result": "0x"}), # EOA
        ]
    )

    out = await adapter.lookup_address(addr)
    assert out["status"] == "ok"
    assert out["chain"] == "ethereum"
    assert out["summary"]["balance"] == 1.0
    assert out["summary"]["is_contract"] is False
