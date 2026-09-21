"""Pytest suite verifying FixtureAdapter transaction resolution, hop count, and destination attribution across all 4 scenarios.
Reference: SIH26183 Phase 2 Verification.
"""

import pytest
from app.services.adapters import FixtureAdapter, get_adapter


@pytest.fixture
def adapter():
    return FixtureAdapter()


def trace_path_through_adapter(adapter: FixtureAdapter, start_address: str, chain: str, max_hops: int = 15):
    """Helper simulating hop traversal using adapter.get_transactions."""
    current_addr = start_address
    current_chain = chain
    visited_hops = []

    for _ in range(max_hops):
        txs = adapter.get_transactions(current_addr, current_chain)
        # Find outgoing transactions from current_addr
        outgoing = [tx for tx in txs if tx.from_address.lower() == current_addr.lower()]
        if not outgoing:
            break

        # Follow dominant value outgoing transaction
        dominant_tx = max(outgoing, key=lambda t: t.value)
        visited_hops.append(dominant_tx)

        current_addr = dominant_tx.to_address
        current_chain = dominant_tx.chain

        # Check if we landed on a cross-chain bridge or target chain shift
        if dominant_tx.metadata.get("cross_chain_target"):
            current_chain = dominant_tx.metadata["cross_chain_target"]

        # Check if we reached a known VASP hot wallet
        vasp_match = adapter.is_vasp_hot_wallet(current_addr, current_chain)
        if vasp_match:
            break

    return visited_hops, current_addr


def test_scenario_1_direct_sweep_to_coindcx(adapter):
    """Scenario 1: Suspect address is 2 hops from labeled/swept CoinDCX hot wallet."""
    suspect_addr = "0x71C8364f9b81A0789C1a5619A07EbfA5fB22910A"
    hops, final_destination = trace_path_through_adapter(adapter, suspect_addr, "ETH")

    # Assert hop count
    assert len(hops) == 2, f"Expected exactly 2 hops, got {len(hops)}"
    assert hops[0].from_address.lower() == suspect_addr.lower()
    assert hops[1].is_sweep is True, "Second hop should be marked as sweep"

    # Assert final destination is CoinDCX
    vasp = adapter.is_vasp_hot_wallet(final_destination)
    assert vasp is not None, "Final destination must match a known VASP hot wallet"
    assert vasp["entity_name"] == "CoinDCX", f"Expected CoinDCX, got {vasp['entity_name']}"
    assert "0xCoinDCX_HotWallet_ETH_FIXTURE_1".lower() == final_destination.lower()


def test_scenario_2_fanout_mixer_converging_at_wazirx(adapter):
    """Scenario 2: Fan-out into privacy mixer pattern converging at WazirX hot wallet."""
    suspect_addr = "0x3a9F784260D672b15Fa0e20f18837138096c7B22"

    # Verify suspect address has multiple outgoing transactions (Fan-Out)
    initial_txs = adapter.get_transactions(suspect_addr, "ETH")
    outgoing_splits = [tx for tx in initial_txs if tx.from_address.lower() == suspect_addr.lower()]
    assert len(outgoing_splits) == 3, f"Expected fan-out into 3 mules, got {len(outgoing_splits)}"

    hops, final_destination = trace_path_through_adapter(adapter, suspect_addr, "ETH")

    # Assert hop count through dominant branch
    assert len(hops) == 5, f"Expected 5 hops through mixer convergence, got {len(hops)}"

    # Assert intermediate typology touches mixer
    hop_targets = [h.to_address.lower() for h in hops]
    assert any("tornadocash" in t for t in hop_targets), "Must route through mixer contract"

    # Assert final destination is WazirX
    vasp = adapter.is_vasp_hot_wallet(final_destination)
    assert vasp is not None, "Final destination must match a known VASP hot wallet"
    assert vasp["entity_name"] == "WazirX", f"Expected WazirX, got {vasp['entity_name']}"
    assert "0xWazirX_HotWallet_ETH_FIXTURE_1".lower() == final_destination.lower()


def test_scenario_3_crosschain_bridge_to_zebpay(adapter):
    """Scenario 3: Cross-chain hop (ETH -> Bridge Router -> TRON) landing at ZebPay."""
    suspect_addr = "0x892a0194856cD192801F6281983017A8128919a0"
    hops, final_destination = trace_path_through_adapter(adapter, suspect_addr, "ETH")

    # Assert hop count across chains
    assert len(hops) == 3, f"Expected 3 hops across bridge, got {len(hops)}"

    # First hop on ETH, subsequent on TRON
    assert hops[0].chain == "ETH"
    assert hops[1].chain == "TRON"
    assert hops[2].chain == "TRON"

    # Assert final destination is ZebPay
    vasp = adapter.is_vasp_hot_wallet(final_destination)
    assert vasp is not None, "Final destination must match a known VASP hot wallet"
    assert vasp["entity_name"] == "ZebPay", f"Expected ZebPay, got {vasp['entity_name']}"
    assert "TR7ZebPay_HotWallet_TRX_FIXTURE_1".lower() == final_destination.lower()


def test_scenario_4_long_weak_path_no_confident_off_ramp(adapter):
    """Scenario 4: Long 8-hop peeling chain terminating at an unverified P2P cluster."""
    suspect_addr = "0x992dE819385610293751a09281754910284759A1"
    hops, final_destination = trace_path_through_adapter(adapter, suspect_addr, "ETH")

    # Assert 8 hops reached
    assert len(hops) == 8, f"Expected 8 hops, got {len(hops)}"

    # Assert final destination is NOT an exchange hot wallet
    vasp = adapter.is_vasp_hot_wallet(final_destination)
    assert vasp is None, "Scenario 4 must NOT reach a known exchange hot wallet"
    assert "0xUnverified_P2P_OTC_Cluster_FIXTURE".lower() == final_destination.lower()


def test_vasp_directory_integrity(adapter):
    """Confirm all 6 seeded Indian VASPs are present and marked with illustrative note."""
    vasp_list = adapter.get_vasp_directory()
    assert len(vasp_list) >= 6

    names = {v["entity_name"] for v in vasp_list}
    expected_names = {"CoinDCX", "WazirX", "ZebPay", "CoinSwitch", "Mudrex", "Giottus"}
    assert expected_names.issubset(names), f"Missing expected VASPs. Found: {names}"

    for v in vasp_list:
        assert len(v["hot_wallet_addresses"]) > 0
        if v["entity_name"] in expected_names:
            assert v["fiu_ind_registered"] is True
        assert v["nodal_contact"] is not None
        assert "illustrative" in v["address_note"].lower()
