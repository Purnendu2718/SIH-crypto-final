# CryptoTrace Sentinel (SIH26183) — Universal Blockchain Forensics

An open-source, law-enforcement-grade blockchain forensics search and investigation platform for Indian Law Enforcement Agencies (MHA / I4C). Built with **FastAPI + Python 3.12+**, **React 18 + Vite + TypeScript + Tailwind CSS**, and multi-chain cryptographic validators.

---

## Key Capabilities

- **Single-Box Universal Search**: Accepts any cryptocurrency wallet address or transaction hash across Bitcoin, Ethereum & EVM chains, TRON, Solana, XRP Ledger, Stellar, UTXO forks (LTC, DOGE, DASH, ZEC, BCH), Cardano, and Monero.
- **Strict Cryptographic Checksum Validation**: Powered by `address_validator.py` (stdlib only) with Base58Check, Bech32/Bech32m (BIP-173/BIP-350), EIP-55 mixed-case Keccak-256, and CashAddr verification.
- **Live On-Chain Forensics**: Real-time balance, transaction count, recent transaction history, public explorer links, and entity attribution.
- **Privacy Chain Awareness**: Identifies privacy chains (e.g. Monero) and safely explains why on-chain address queries are not applicable.
- **Security & SSRF Hardening**: Fixed allowlist for upstream providers, URL-encoding of normalized inputs, strict 10s timeouts, exponential backoff retries, in-memory TTL caching, and zero secret logging or client exposure.
- **Section 65B BSA / 94 BNSS Legal Compliance**: Cryptographic audit trails, court-ready evidence generation, and immutable Merkle-verified run summaries.

---

## Architecture

```
sih3-cld/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI entry point, CORS, global 500 error handler
│   │   ├── routers/
│   │   │   ├── search.py               # POST /api/v1/search, /validate, /analysis/{run_id}
│   │   │   └── ...
│   │   └── services/
│   │       ├── address_validator.py    # Single source of truth for address validation
│   │       └── providers/              # Multi-chain live data adapters
│   │           ├── base.py             # ChainAdapter ABC, SSRF allowlist, retries, caching
│   │           ├── bitcoin.py          # Mempool.space Esplora + Blockstream fallback
│   │           ├── tron.py             # TronGrid API
│   │           ├── solana.py           # Solana JSON-RPC
│   │           ├── xrp.py              # XRPL JSON-RPC
│   │           ├── stellar.py          # Stellar Horizon REST
│   │           ├── evm.py              # Ethereum & EVM JSON-RPC + Etherscan V2
│   │           ├── blockchair.py       # LTC, DOGE, DASH, ZEC, BCH via Blockchair
│   │           ├── cardano.py          # Koios REST API
│   │           ├── monero.py           # Monero privacy handler (not_applicable)
│   │           ├── unsupported.py      # Cosmos / Substrate handler (unsupported_lookup)
│   │           ├── registry.py         # Adapter singleton registry
│   │           └── entities.py         # Known entities attribution loader
│   └── tests/
│       ├── test_validator.py           # 29 address validator unit tests
│       └── test_multi_chain_search.py  # 11 respx-mocked integration tests
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AddressSearchComponent.tsx # Interactive forensic inspector
│   │   │   └── AddressSearchModal.tsx     # Modal wrapper for search & inspector
│   │   └── lib/
│   │       └── api.ts                  # Typed API client
│   └── vite.config.ts                  # Dev server with /api proxy
└── scripts/
    ├── smoke_live.py                   # Live upstream provider smoke tester
    └── browser_test_and_screenshot.py  # Chrome CDP end-to-end automation
```

---

## Adding a Chain

Extending CryptoTrace Sentinel to support a new blockchain requires two distinct, decoupled steps: adding the cryptographic validation rule in `address_validator.py`, and implementing the network query adapter in `backend/app/services/providers/`.

### Step 1: Add Address & Tx Validation in `address_validator.py`

`address_validator.py` is the single source of truth for query identification. It uses Python standard library only (no third-party dependencies):

1. **Define Checksum or Format Rules**:
   - If the chain uses a standard algorithm (e.g., Base58Check, Bech32, EIP-55 Keccak-256, Crockford Base32, CRC16/Polymod):
     - Reuse the existing stdlib functions (`_base58_decode_check`, `_bech32_decode`, `_eip55_checksum`).
     - Or implement the mathematical checksum verification helper without third-party libraries.
2. **Add Detection Logic to `validate(query)`**:
   - Add regex pattern matching for the chain's address prefix and character set.
   - For checksummed chains:
     - If the checksum passes, append candidate: `Candidate(chain="new_chain", address_type="standard", network="mainnet", checksum_verified=True)` and set `certainty = Certainty.VERIFIED`.
     - If the format matches but the checksum fails, do **not** mark valid; set `error` (e.g. `"Invalid NewChain checksum: typo detected"`) and a helpful `hint`.
   - For non-checksummed chains:
     - Set `checksum_verified=False` and `certainty = Certainty.FORMAT_ONLY` (explaining that typos cannot be mathematically detected).
3. **Add Unit Tests in `test_validator.py`**:
   - Add valid mainnet address test vectors.
   - Add valid testnet address test vectors (if applicable).
   - Add 1-character corrupted address vectors to verify checksum rejection.
   - Run: `python -m unittest test_validator` (all tests must stay green).

### Step 2: Implement the Chain Provider Adapter

Create a new adapter in `backend/app/services/providers/` extending `ChainAdapter`:

```python
# backend/app/services/providers/new_chain.py
from typing import Optional, List
from .base import ChainAdapter, ChainSummary, TransactionItem, LookupResult, Status

class NewChainAdapter(ChainAdapter):
    def __init__(self, rpc_url: Optional[str] = None):
        super().__init__()
        self.rpc_url = rpc_url or "https://rpc.newchain.org"

    async def lookup_address(self, address: str, network: str = "mainnet") -> LookupResult:
        # 1. Normalize and URL-encode input
        safe_addr = self.encode_query(address)
        target_url = f"{self.rpc_url}/api/v1/account/{safe_addr}"
        
        # 2. SSRF check is handled automatically by self.get()
        try:
            resp = await self.get(target_url)
            if resp.status_code == 404:
                return self.make_result("new_chain", network, Status.NOT_FOUND, source="NewChain Explorer", source_url=target_url)
            resp.raise_for_status()
            data = resp.json()
            
            # 3. Parse balance, tx_count, transactions
            summary = ChainSummary(
                balance=float(data.get("balance", 0)),
                balance_formatted=f"{data.get('balance')} NEW",
                tx_count=int(data.get("tx_count", 0)),
            )
            return self.make_result(
                "new_chain",
                network,
                Status.OK,
                summary=summary,
                transactions=[],
                source="NewChain Explorer",
                source_url=target_url,
            )
        except Exception as e:
            return self.make_result(
                "new_chain", network, Status.UNAVAILABLE, error=str(e), source="NewChain Explorer", source_url=target_url
            )

    async def lookup_tx(self, tx_hash: str, network: str = "mainnet") -> LookupResult:
        # Implement transaction hash lookup or return NOT_FOUND if hash is not present on this chain
        ...
```

### Step 3: Register the Adapter in `registry.py` and SSRF Allowlist

1. **Register Allowed Hosts** in `backend/app/services/providers/base.py`:
   - Add the provider's hostname to `ALLOWED_HOSTS` (e.g., `'rpc.newchain.org'`).
2. **Register the Chain Key** in `backend/app/services/providers/registry.py`:
   - Map `'new_chain'` to the new adapter instance in `AdapterRegistry._init_adapters()`.
3. **Add Environment Variables** to `.env.example`:
   - Document any optional API keys or custom RPC endpoints (e.g., `NEWCHAIN_RPC_URL`).

### Step 4: Verification

1. **Integration Mock Tests**: Add respx mock tests in `backend/tests/test_multi_chain_search.py` verifying 200 OK, 404 not_found, and 500 unavailable responses.
2. **Live Smoke Test**: Add a test address to `scripts/smoke_live.py` and run:
   ```bash
   python scripts/smoke_live.py
   ```
3. **Frontend Verification**: Build and test the frontend:
   ```bash
   cd frontend
   npm run build
   ```

---

## Running Verification & Tests

### 1. Address Validator Unit Tests
```bash
python -m unittest test_validator
```
*(All 29 tests pass with stdlib Python).*

### 2. Backend Integration Tests (Mocked with respx)
```bash
pytest backend/tests/test_multi_chain_search.py -v
```

### 3. Live Provider Smoke Test
```bash
python scripts/smoke_live.py
```
Outputs a live table querying real mainnet RPC/explorer APIs across 7 chains.

### 4. Frontend Type-Check & Build
```bash
cd frontend
npm run build
```

---

## License & Attribution
- Reference Standard: **MHA / I4C — Smart India Hackathon (SIH26183)**.
- Evidence Compliance: **Section 65B Indian Evidence Act (BSA Section 63) / BNSS Section 94**.
