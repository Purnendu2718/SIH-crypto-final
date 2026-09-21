"""Live smoke test script for CryptoTrace Sentinel multi-chain providers.
Calls live providers for reference addresses and prints an audit table.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure backend package is on sys.path
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.abspath(os.path.join(_here, ".."))
_backend = os.path.join(_root, "backend")
_services = os.path.join(_backend, "app", "services")
for p in (_root, _backend, _services):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.services.address_validator import validate
from app.services.providers.registry import get_provider_adapter

TEST_ADDRESSES = [
    ("Bitcoin Genesis", "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"),
    ("Bitcoin Block-170", "12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S"),
    ("Ethereum Sample", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"),
    ("TRON Tether", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"),
    ("Solana System", "11111111111111111111111111111111"),
    ("XRP Genesis", "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"),
    ("Stellar Anchor", "GAAZI4TCR3TY5OJHCTJC2A4QSY6CJWJH5IAJTGKIN2ER7LBNVKOCCWN7"),
]


async def run_smoke():
    print("=" * 90)
    print("CryptoTrace Sentinel — Multi-Chain Provider Live Smoke Test")
    print("=" * 90)
    print(f"{'Label':<18} | {'Chain':<12} | {'Status':<13} | {'Tx Count':<9} | {'Balance':<20} | {'Source'}")
    print("-" * 90)

    rows = []
    for label, addr in TEST_ADDRESSES:
        val = validate(addr)
        if not val.is_valid or not val.candidates:
            print(f"{label:<18} | {'UNKNOWN':<12} | {'invalid_format':<13} | {'-':<9} | {'-':<20} | Validator")
            continue

        primary = val.primary or val.candidates[0]
        chain_name = primary.chain
        adapter = get_provider_adapter(chain_name)

        try:
            res = await adapter.lookup_address(val.normalized, network=primary.network)
            status = res.get("status", "unknown")
            summary = res.get("summary", {})
            tx_count = str(summary.get("tx_count", "-"))
            bal = summary.get("balance_formatted") or str(summary.get("balance", "-"))
            source = res.get("source", adapter.source_name)
            error = res.get("error")

            rows.append({
                "label": label,
                "chain": chain_name,
                "status": status,
                "tx_count": tx_count,
                "balance": bal,
                "source": source,
                "error": error,
            })

            print(f"{label:<18} | {chain_name:<12} | {status:<13} | {tx_count:<9} | {bal:<20} | {source}")
            if error and status == "unavailable":
                print(f"   ↳ Provider error note: {error}")

        except Exception as e:
            print(f"{label:<18} | {chain_name:<12} | {'crashed':<13} | {'-':<9} | {'-':<20} | Error: {e}")

    print("=" * 90)
    print("Smoke test completed without crashing.")
    return rows


if __name__ == "__main__":
    asyncio.run(run_smoke())
