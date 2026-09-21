# CryptoTrace Sentinel: paste-once Antigravity prompt

## Before you paste (2 minutes)

1. Copy `address_validator.py` and `test_validator.py` into your project folder (the repo root is fine; the prompt tells Antigravity to move them to the right place).
2. Open the project in Antigravity, switch to **Planning** mode, start a new conversation.
3. Paste everything below the line. One paste, no follow-ups needed. If it stops early, reply: `continue from where you stopped`.

---

You are a senior full-stack engineer working in this repository (CryptoTrace Sentinel, a blockchain forensics search tool for law-enforcement style investigations; frontend is Vite + React + TypeScript + Tailwind). Work autonomously and in order. Ask a question only if you are truly blocked.

## The problem to solve

Searching Satoshi's genesis address `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` returns "invalid format". The goal: the search box accepts any real wallet address or transaction hash, identifies the chain(s) with checksum-level precision, and then shows **real on-chain data** for it.

I have added two tested files to the workspace: `address_validator.py` (stdlib only) and `test_validator.py` (29 tests, all passing). The validator is the single source of truth for what counts as a valid address. It returns a `ValidationResult` (`validate(query)` / `.to_dict()`) with: `is_valid`, `kind` (`address` | `transaction_hash` | `ens_name` | `unknown`), `certainty` (`verified` | `format_only` | `none`), `candidates[]` (`chain`, `address_type`, `network`, `checksum_verified`, `note`), `related_chains[]`, `normalized`, `error`, `hint`.

## Non-negotiable rules

1. **Do not change the validation logic in `address_validator.py`.** Keep `python -m unittest test_validator` green at every step. If you believe it is wrong for some input, add a failing test that proves it with a published vector and report it; do not silently patch it.
2. **Never fabricate on-chain data.** No mock or fixture data in the real search path. If a provider call fails, return `status: "unavailable"` with the reason. Demo data is allowed only behind `DEMO_MODE=true`, and then every response carries `"demo": true` and the UI shows a visible banner.
3. **Validate on the server, always** (via `validate()`), regardless of any frontend validation. Never build provider URLs from raw user input: use the validator's `normalized` value, URL-encode it, and only call hosts from a fixed allowlist (SSRF protection).
4. **Provider calls happen only in the backend.** API keys come from environment variables, are never hard-coded, never logged, never sent to the browser. Provide `.env.example`.
5. Every provider call has a 10 s timeout, max 2 retries with backoff on 429/5xx, a small in-memory TTL cache (60 s), and a per-provider concurrency limit.
6. Every result carries evidence metadata: `source` (provider name), `source_url` (without keys), `fetched_at` (UTC ISO 8601).
7. Provider APIs change. **Before writing each adapter, open the provider's current official docs and confirm the endpoint and response shape.** If they differ from what is written below, follow the docs and note it in your report.
8. No unrelated refactors. Match the existing code style and folder structure.

## Step 0: Recon (do not skip)

Inspect the repo tree, `package.json`, `vite.config.ts`, the Dockerfile and any backend. Find where the current "invalid format" logic lives (grep for `invalid format`, address regexes, `validate`). If there is no backend yet, create a FastAPI app under `backend/` with a `requirements.txt` (fastapi, uvicorn, httpx, pydantic, pytest, pytest-asyncio, respx). Write a 10-line summary of what you found, then continue.

## Step 1: Replace validation everywhere

Move `address_validator.py` and `test_validator.py` into the backend package. Delete every old address regex/validator (frontend and backend). All validation goes through `validate()`. Keep `POST /api/v1/validate-address` as a backward-compatible alias and add `POST /api/v1/validate` (pure, no network, safe for as-you-type use) returning `ValidationResult.to_dict()`.

## Step 2: Search API

`POST /api/v1/search` with `{ "query": string, "case_id"?: string, "all_candidates"?: boolean }`.

- Invalid input: HTTP 422 with `{ "validation": {...} }` so the UI can show `error` and `hint`.
- `kind == "ens_name"`: return the validation object plus `status: "needs_resolution"` (do not guess an address).
- Valid address: look up the **primary candidate's chain**; with `all_candidates=true`, also look up the other candidates concurrently (`asyncio.gather`). For EVM addresses, "primary" means Ethereum; `related_chains` are the other EVM chains, queried only when `all_candidates=true`.
- Valid transaction hash: probe the candidate chains concurrently and return those where the hash is found.
- Response: `{ run_id, query, validation, results: [ { chain, network, status, summary, transactions, labels, source, source_url, fetched_at, error } ] }` where `status` is one of `ok | not_found | unavailable | not_applicable | unsupported_lookup`.
- Also `GET /api/v1/analysis/{run_id}` (in-memory store is fine for now) and `GET /api/health`.
- Fix the global exception handler to return a proper `JSONResponse` with a 500 status. Restrict CORS to the configured frontend origin(s) via env, not `*`.

## Step 3: Provider adapters

Create a `ChainAdapter` interface (`lookup_address`, `lookup_tx`) and one adapter per row. Balance, tx count, first/last activity where the provider gives it, and the 20 most recent transactions.

| Chain | Provider (verify in docs first) | Key needed |
|---|---|---|
| bitcoin (mainnet/testnet) | mempool.space Esplora API: `/api/address/{addr}` (chain_stats and mempool_stats: funded_txo_sum, spent_txo_sum, tx_count), `/api/address/{addr}/txs`, `/api/tx/{txid}`; testnet under `/testnet/api`. Balance = funded minus spent (satoshis). Fallback: blockstream.info Esplora (same schema). | no |
| tron | TronGrid `/v1/accounts/{address}` and `/v1/accounts/{address}/transactions` | optional `TRON_PRO_API_KEY` |
| solana | JSON-RPC `getBalance`, `getSignaturesForAddress`, `getAccountInfo` at `SOLANA_RPC_URL` (default public mainnet RPC) | no |
| xrp_ledger | XRPL JSON-RPC `account_info`, `account_tx` (`actNotFound` means `not_found`, i.e. unfunded) | no |
| stellar | Horizon `/accounts/{id}`, `/accounts/{id}/transactions?order=desc&limit=20` (404 means `not_found`) | no |
| ethereum + other EVM chains | Balance/nonce/contract-or-EOA via public JSON-RPC (`eth_getBalance`, `eth_getTransactionCount`, `eth_getCode`), URLs overridable per chain by env. Transaction history via **Etherscan API V2** (single key, `chainid` parameter; V1 endpoints are deprecated) | `ETHERSCAN_API_KEY` for history; without it return balance/nonce only and say history needs the key |
| litecoin, dogecoin, dash, zcash, bitcoin_cash | Blockchair `/{blockchain}/dashboards/address/{addr}` | optional `BLOCKCHAIR_API_KEY` |
| cardano | Koios `address_info` | no |
| monero | **No lookup.** Return `status: "not_applicable"` with the note from the candidate: privacy chain, balance and history cannot be derived from an address. | n/a |
| cosmos family, polkadot/kusama, others | Validation only. Return `status: "unsupported_lookup"` with a clear message (do not pretend). | n/a |

Also add `data/known_entities.json` with a loader that attaches `labels` to results. Seed it with exactly one entry, sourced and phrased carefully: the Bitcoin genesis-block coinbase address, "widely attributed to Satoshi Nakamoto (genesis block reward)". Every entry needs `label`, `source`, `confidence`. Never invent labels.

## Step 4: Frontend

The old `AddressSearchComponent.tsx` (if present in the repo from earlier work) has known bugs. Fix or replace it inside the existing app shell and design system:
- `process.env.REACT_APP_API_URL` does not work in Vite. Use `import.meta.env.VITE_API_URL`, and add a dev proxy for `/api` in `vite.config.ts`.
- `handleSearch` awaits validation and then reads the *stale* `validationResult` state, so the real search never runs. Use one call to `/api/v1/search` and render from its response. Remove `alert()` usage.
- UI: one search box (placeholder shows several chain examples); a validation card showing chain candidates, address type, network, and a **certainty badge**: "Checksum verified" vs "Format only: this chain has no checksum, a typo cannot be detected" (Solana and lowercase EVM). Show the validator's `error` and `hint` verbatim on failure. When several chains are candidates (EVM, legacy `3...`/`1...`), say so plainly and offer a "check other chains" button (`all_candidates=true`).
- Results: one card per chain with balance, tx count, recent-transactions table (hash, time, amount, link to a public explorer), evidence footer (source, fetched_at). Separate states for loading (skeleton), `not_found`, `unavailable`, `not_applicable`, `unsupported_lookup`, and a visible DEMO banner if `demo: true`.
- Sample chips: the genesis address `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa`, an EVM address `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed`, TRON `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`. Copy-to-clipboard on addresses; monospace; keyboard and screen-reader friendly.

## Step 5: Verification (run everything, do not just write it)

1. `python -m unittest test_validator` must pass.
2. Add backend pytest tests: adapters against recorded provider responses using `respx` (fixtures live only under `tests/`); endpoint tests covering the genesis address (200, `validation.primary.chain == "bitcoin"`), a one-character-corrupted genesis address (422 with hint), an ENS name, a 64-hex tx hash, and a Monero address (`not_applicable`).
3. Write `scripts/smoke_live.py` that calls the real providers for: the genesis address, `12cbQLTFMXRnSzktFkuoG3eHoMeFtpTu3S`, the EVM sample above, the TRON sample, Solana `11111111111111111111111111111111`, XRP `rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh`, Stellar `GAAZI4TCR3TY5OJHCTJC2A4QSY6CJWJH5IAJTGKIN2ER7LBNVKOCCWN7`. Print a table of `chain | status | tx_count | balance | source`. Run it. A provider being down must not crash the script, but must appear in the report.
4. Start backend and frontend, and use the browser to search the genesis address. Capture a screenshot showing the validation card and the on-chain result.
5. `npm run build` and the type-check must pass.

## Definition of done

- The genesis address is accepted, identified as Bitcoin P2PKH with "Checksum verified", and shows real live data with source and timestamp.
- A one-character typo in any checksummed address is rejected with a specific message.
- No mock data appears anywhere in the real path; failures show as `unavailable`, not as empty success.
- All tests pass; `.env.example` lists every variable; README section "Adding a chain" explains how to add a validator and an adapter.

## Final report (required, plain and honest)

List: files changed; the recon findings; what you **ran and saw pass** (paste the smoke table and test summary); what you could **not** verify (e.g. no network, missing API keys) and exactly what the user must set to enable it; any docs-vs-prompt endpoint differences you found; anything you were tempted to fake and did not.
