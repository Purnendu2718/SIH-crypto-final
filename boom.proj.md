# CryptoTrace Sentinel — Antigravity Build Plan
### SIH26183 · Feed this into Google Antigravity in phases. Read "Feeding Instructions" at the very end before you paste anything.

---

## 0. Master Context Block

Paste this once at the start of the Antigravity session (Planning mode), or save it into the repo as `PROJECT.md` and reference it with `@PROJECT.md` in every phase prompt below. Do this **before** Phase 0.

```
PROJECT: CryptoTrace Sentinel (SIH26183)

WHAT IT IS: An open-source, self-hostable blockchain-forensics platform for Indian
law enforcement. It takes a victim-reported suspect crypto wallet address, traces
its fund flow across hops, attributes the receiving exchange/VASP with an
explainable confidence score, detects laundering typologies, and produces a
court-ready evidence package plus a pre-drafted Section 94 BNSS statutory notice.

NON-NEGOTIABLE PRINCIPLES (apply to every phase, no exceptions):
1. Decision support, not legal determination. Every attribution carries a
   confidence band. Below MEDIUM confidence, the system must say "insufficient
   evidence" — never force a guess.
2. Explainable over black-box. Every score must show which rule fired and its
   weight. No opaque ML scoring in the MVP.
3. Offline-first. A seeded fixture/demo dataset must be the default data source
   so the app runs and demos fully without any live network access or API keys.
   Live chain-provider adapters are an additive, swappable layer, never a hard
   dependency of the demo path.
4. RBAC + audit log on every write. Every case/evidence action is attributed to
   the acting officer and appended to a hash-chained audit log.
5. No secrets in code, ever. All keys/URLs come from environment variables with
   a checked-in .env.example that has placeholder values only.

TECH STACK:
- Backend: FastAPI (Python 3.11+), SQLAlchemy, Pydantic v2
- Database + Auth: Supabase (Postgres + Supabase Auth, email/password)
- Frontend: React + Vite (or Next.js App Router — pick one and stay consistent),
  Cytoscape.js for graph visualization, Tailwind for styling
- Graph/trace engine: plain Python BFS/NetworkX to start — do NOT reach for a
  custom C extension; profile first, optimize only if a real bottleneck shows up
- Async jobs (production path only, not required for MVP demo): Celery + Redis
- PDF generation: ReportLab or WeasyPrint
- Deployment: Docker Compose, Nginx as single reverse-proxy entry point

REPO LAYOUT (target):
backend/
  app/
    main.py                 FastAPI app + router wiring
    config.py                Env-driven settings, SQLite fallback for pure-local dev
    models.py                  SQLAlchemy models
    schemas.py                   Pydantic schemas
    security.py                    Supabase JWT verification + RBAC dependency
    fixtures/demo_dataset.json       Seeded offline scenario data
    services/
      adapters/                      chain adapter interface + FixtureAdapter (+ evm/tron/btc later)
      trace_engine.py                  multi-hop BFS / shortest-path-to-off-ramp
      attribution.py                     weighted scoring (§ see PROJECT spec doc)
      typology.py                          fan-out / peeling / mixer / layering rules
      taint_engine.py                        FIFO contamination accounting
      risk_engine.py                           composite risk score
      evidence.py                                SHA-256 hash + Merkle root + audit chain
      legal_notice.py                              Section 94 BNSS notice generator
      report_generator.py                            PDF evidence package (ReportLab)
    routers/                    auth, cases, wallets, analysis, evidence, audit, watchlist, intel
    tests/
frontend/
  src/
    pages/ (or app/)     Login, Dashboard, CaseDetail, GraphView, EvidenceDrawer
    components/          GraphCanvas, ForensicDrawer, EvidenceView, CourtPresentationMode
    lib/api.ts           typed API client
docker-compose.yml
PROJECT.md              (this context block, saved to disk)

REFERENCE PROBLEM STATEMENT ID: SIH26183, Ministry of Home Affairs / I4C,
"Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from
Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics."
```

---

## 1. Supabase Schema & Auth (reference — implemented in Phase 1)

```sql
-- profiles: one row per officer, keyed to Supabase auth.users
create table profiles (
  id uuid primary key references auth.users(id),
  full_name text not null,
  badge_no text,
  role text not null check (role in ('INVESTIGATOR','SUPERVISOR','ADMIN')),
  district text,
  created_at timestamptz default now()
);

create table cases (
  case_id uuid primary key default gen_random_uuid(),
  ncrp_ref text,
  victim_utr text,
  amount_inr numeric,
  assigned_officer_id uuid references profiles(id),
  status text default 'OPEN',
  created_at timestamptz default now()
);

create table wallet_submissions (
  submission_id uuid primary key default gen_random_uuid(),
  case_id uuid references cases(case_id),
  chain text not null,
  address text not null,
  submitted_at timestamptz default now()
);

create table analysis_runs (
  run_id uuid primary key default gen_random_uuid(),
  submission_id uuid references wallet_submissions(submission_id),
  status text default 'PENDING',
  started_at timestamptz default now(),
  completed_at timestamptz
);

create table trace_paths (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(run_id),
  hop_index int, from_addr text, to_addr text, tx_hash text, chain text, value numeric
);

create table attributions (
  run_id uuid references analysis_runs(run_id),
  matched_entity text, rule_fired text, confidence numeric, score_breakdown jsonb
);

create table typologies_detected (
  run_id uuid references analysis_runs(run_id), typology text, hop_start int, hop_end int
);

create table evidence_packages (
  package_id uuid primary key default gen_random_uuid(),
  run_id uuid references analysis_runs(run_id),
  sha256_hash text, merkle_root text, generated_at timestamptz default now()
);

create table audit_log (
  entry_id uuid primary key default gen_random_uuid(),
  prev_hash text, entry_hash text,
  officer_id uuid references profiles(id),
  action text, target_id text, timestamp timestamptz default now()
);

create table vasp_directory (
  entity_name text primary key, chain text, hot_wallet_addresses text[],
  fiu_ind_registered boolean, sla_hours numeric, nodal_contact text
);

create table watchlist_entries (
  id uuid primary key default gen_random_uuid(),
  address text, chain text, case_id uuid references cases(case_id), alert_channel text
);

create table intel_tags (
  address_hash text primary key, tag text, district text,
  submitted_by uuid references profiles(id), submitted_at timestamptz default now()
);

-- Row Level Security
alter table cases enable row level security;
create policy investigator_own_cases on cases
  for select using (
    assigned_officer_id = auth.uid()
    or exists (select 1 from profiles p where p.id = auth.uid() and p.role in ('SUPERVISOR','ADMIN'))
  );
-- Mirror equivalent RLS on wallet_submissions/analysis_runs/attributions via case_id join,
-- and on audit_log (officers can read entries they created; SUPERVISOR/ADMIN read all).
```

**Session persistence:** use the Supabase JS client's default behavior (`persistSession: true`, `autoRefreshToken: true`) — this alone satisfies "officer doesn't have to log in every time." Do not build a custom token-storage mechanism; the default is correct and secure.

**Work-history preload:** on the dashboard's initial mount, fire one query joining `cases` → `analysis_runs` → `attributions` filtered by the logged-in officer's `auth.uid()` (or district scope for supervisors), ordered by `created_at desc`, so the caseload is populated before the officer does anything else.

---

## 2. Phased Task Prompts

Each phase below is one paste into Antigravity. **Do not combine phases.** Each ends with a verification instruction — do not approve/move on until that verification actually passes.

### Phase 0 — Repo Scaffolding

```
Using the context in PROJECT.md, scaffold the repo layout exactly as specified
there: backend/ (FastAPI skeleton with an empty main.py that returns a health
check at /api/health), frontend/ (Vite + React skeleton with Tailwind
configured), docker-compose.yml wiring both services plus a Postgres container
for local dev, and a root .env.example with placeholder values for
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL.
Add a Makefile with `up`, `down`, `seed`, `test` targets.
Do not implement any business logic yet — this phase is scaffolding only.
Verification: run `docker compose up --build` and confirm GET /api/health on
the backend returns 200, and the frontend dev server loads a blank page
without console errors.
```

### Phase 1 — Officer Auth Portal (Supabase)

```
Using @PROJECT.md and the Supabase schema in the Supabase Schema section
(paste it into a Supabase migration file under backend/supabase/migrations/),
implement:
- Supabase project wiring on both frontend and backend (backend verifies the
  Supabase JWT on protected routes; frontend uses the Supabase JS client with
  default session persistence).
- Login and signup pages (email + password only for MVP).
- A protected dashboard shell that, immediately on load, queries the logged-in
  officer's cases/analysis runs and renders them as a list — this is the
  "work history preloaded" requirement, it must not be empty/placeholder data
  once real rows exist.
- RBAC: a `profiles` table row is created on signup with role INVESTIGATOR by
  default; add a way (seed script, not UI) to promote a profile to SUPERVISOR
  or ADMIN for testing.
- Apply the RLS policies from the schema so an investigator's query only
  returns their own cases at the database level, not just hidden in the UI.
Verification: create two test officer accounts, log in as each, confirm each
only sees their own seeded cases, log out and back in and confirm the session
did not require re-entering credentials within the token's normal lifetime,
and confirm closing and reopening the browser preserves the session.
```

### Phase 2 — Domain Models, Chain Adapter Interface, Fixture Data

```
Using @PROJECT.md, implement the remaining SQLAlchemy models (wallet_submissions,
analysis_runs, trace_paths, attributions, typologies_detected, evidence_packages,
audit_log, vasp_directory, watchlist_entries, intel_tags) matching the Supabase
schema. Implement the chain-adapter interface in
backend/app/services/adapters/ with one method get_transactions(address, chain)
returning a normalized transaction list, and implement FixtureAdapter as the
only concrete adapter for this phase, reading from
backend/app/fixtures/demo_dataset.json.
Build demo_dataset.json with four scenarios: (1) a suspect address 2 hops from
a labeled/swept exchange hot wallet, HIGH confidence; (2) a fan-out into a
mixer pattern converging at a VASP; (3) a cross-chain hop (ETH -> a named
placeholder bridge contract -> a TRON address) landing at a VASP; (4) a long,
weakly-connected path that should NOT reach VERY_HIGH confidence.
Seed vasp_directory with 5-6 real, publicly known Indian VASP names (WazirX,
CoinDCX, ZebPay, CoinSwitch) with placeholder hot-wallet address lists you'll
mark clearly as illustrative fixture data, not verified real addresses.
Verification: write and run a pytest that calls FixtureAdapter.get_transactions
for each of the 4 scenario addresses and asserts the expected hop count and
final destination for each.
```

### Phase 3 — Trace Engine

```
Using @PROJECT.md, implement backend/app/services/trace_engine.py: a bounded
breadth-first search starting from a submitted wallet address, using the
active chain adapter, following the dominant-value outgoing transaction at
each hop, filtering transactions below a configurable dust threshold, stopping
at a configurable max hop count (default 15), and stopping early if it reaches
an address present in vasp_directory.hot_wallet_addresses. Persist the
resulting path to trace_paths. If the hop budget is exhausted without reaching
a known entity, mark the run's status as NO_CONFIDENT_OFF_RAMP rather than
fabricating a destination.
Verification: run the pytest suite against all 4 fixture scenarios and assert
scenario 1 reaches the labeled exchange within 2-3 hops, scenario 4 either
reaches low confidence or NO_CONFIDENT_OFF_RAMP, and no scenario throws.
```

### Phase 4 — Attribution, Risk, Typology, Taint Engines

```
Using @PROJECT.md and the weighted scoring table in the solution proposal
(sweep/label match 0.35, path proximity 0.20, deposit-pattern similarity 0.15,
temporal correlation 0.15, co-spend cluster 0.10, behavioral 0.05), implement:
- services/attribution.py: computes the weighted score per trace_paths result,
  writes matched_entity/rule_fired/confidence/score_breakdown to attributions.
  Confidence bands: VERY_HIGH >=0.85, HIGH >=0.65, MEDIUM >=0.40, else
  INSUFFICIENT_EVIDENCE (must be explicitly returned as a value, never omitted).
- services/typology.py: rule-based detectors for fan-out, peeling chain, mixer,
  layering over the persisted trace_paths, writing hits to typologies_detected.
- services/taint_engine.py: FIFO contamination accounting producing a
  percentage of a wallet's balance attributable to the case's reported theft.
- services/risk_engine.py: a composite 0-100 risk score combining confidence,
  typology hits, and taint ratio, with an explainable per-factor breakdown
  returned in the API response (not just a bare number).
Verification: run pytest covering all 4 fixture scenarios end to end
(trace -> attribution -> typology -> risk) and assert scenario 4 never
produces a confidence above MEDIUM.
```

### Phase 5 — Evidence, Audit Log, Legal Notice, PDF Report

```
Using @PROJECT.md, implement:
- services/evidence.py: for a completed analysis run, compute a SHA-256 hash
  of the serialized raw trace payload, a Merkle root if the evidence package
  has multiple files, and write to evidence_packages.
- audit_log write helper: every case/evidence/notice action appends an entry
  whose entry_hash is a hash of (prev_hash + action + officer_id + timestamp),
  forming a hash chain. Add an endpoint to verify the chain's integrity
  (recompute hashes and confirm no entry was altered).
- services/legal_notice.py: generates a Section 94 BNSS requisition notice
  (plain text or PDF) pre-filled with the exchange's nodal contact from
  vasp_directory, the case's NCRP reference, the suspect address, tx hash(es),
  timestamps, and INR value, ending with the line "Draft for review by the
  investigating officer / department legal cell before issuance."
- services/report_generator.py: a PDF evidence report (ReportLab) combining
  the trace graph summary, attribution breakdown, typology hits, taint ratio,
  and the Section 63 BSA-style certificate (record description, producing
  process, SHA-256 hash, Merkle root, timestamp, and a signature line for the
  officer).
Verification: generate a full evidence package + legal notice for scenario 1,
confirm the PDF opens and contains all listed sections, and confirm the audit
log verification endpoint correctly detects a deliberately corrupted entry in
a test.
```

### Phase 6 — Frontend Investigator Dashboard

```
Using @PROJECT.md, build out the frontend beyond the auth shell from Phase 1:
- Dashboard: officer's case list (already wired in Phase 1), a "new wallet
  submission" form (chain + address + optional case fields).
- CaseDetail page: shows run status, and once complete, the trace graph
  (Cytoscape.js — nodes for addresses, edges for transactions, distinct
  styling for the hop that triggered the attribution match).
- ForensicDrawer component: shows the attribution score breakdown, typology
  hits, and taint ratio in the explainable per-factor format from Phase 4 —
  do not just show a bare confidence number.
- EvidenceView component: lets the officer download the PDF report and view
  the raw evidence JSON with its hash displayed.
- A "Court Presentation Mode" toggle on CaseDetail that swaps the technical
  graph view for a simplified chronological, rupee-denominated timeline.
Verification: run the full flow in a browser for scenario 1 end to end —
log in, submit the fixture wallet address, watch the run complete, open the
graph, open the forensic drawer, download the evidence PDF, toggle Court
Presentation Mode — with no console errors at any step.
```

### Phase 7 — India-Specific Innovation Layer (build only after Phase 0-6 are demo-stable)

```
Using @PROJECT.md, implement, as independent additions that do not modify the
Phase 0-6 core flow:
- UPI-UTR correlator: a case field for victim-submitted UTR + amount + rough
  timestamp; a matching heuristic that flags on-chain deposits within a
  configurable time/amount tolerance window as a correlated candidate.
- Golden Hour watchlist: watchlist_entries CRUD, and a polling job (interval
  configurable, default short for demo) that re-runs the fixture/live adapter
  against watchlisted addresses and fires a webhook (stub a Telegram webhook
  call behind a feature flag, not a hard dependency) if a new outbound
  transaction toward a known off-ramp is detected.
- VASP directory admin view: lets an ADMIN edit vasp_directory entries
  (name, hot wallets, fiu_ind_registered, sla_hours, nodal_contact) from the UI
  instead of only via seed data.
- Police Intel Exchange: an endpoint to submit a SHA-256 hash of an address
  plus a tag and district (never the raw address or victim PII) to
  intel_tags, and a lookup endpoint any authorized officer can query by
  hashing an address client-side and checking for a match — explicitly a
  hash-and-RBAC design, not a zero-knowledge-proof system, and it should be
  built and described that way.
- "Arjuna" co-pilot: an endpoint that takes a completed case's structured
  fields and produces a plain-English (and optionally Hindi) prose summary
  via an LLM call, explicitly instructed to only restate fields already in
  the case record and never introduce new claims.
Verification: each feature has its own isolated test; confirm none of them
break the Phase 0-6 verification steps when run together.
```

### Phase 8 — Real-Time Live Search & Live Chain Adapters

```
Using @PROJECT.md, add real-time, live-network capability as an additive mode
alongside the existing FixtureAdapter — do not remove or change fixture/offline
behavior; it must remain the default when live mode is off.

1. MODE TOGGLE: add a LIVE_MODE environment flag. When unset/false, the app
   behaves exactly as before (FixtureAdapter only, fully air-gapped, zero
   outbound network calls). When true, live adapters below become active,
   with FixtureAdapter as the automatic fallback if any live call fails.

2. LIVE ADAPTERS (implement each behind the same chain-adapter interface from
   Phase 2):
   - EvmLiveAdapter: call an RPC provider (EVM_RPC_URL env var — Alchemy,
     Infura, or a public RPC) using eth_getTransactionByHash and
     eth_getTransactionReceipt so a transaction from the last few minutes is
     read directly rather than waiting on an indexer, PLUS an
     Etherscan-compatible REST API (ETHERSCAN_API_KEY env var) for historical
     address transaction lists.
   - TronLiveAdapter: TronGrid REST API (TRONGRID_API_KEY optional — works at
     a lower rate limit without one) for both recent and historical data.
   - BtcLiveAdapter: mempool.space (or Blockstream Esplora) REST API — these
     surface unconfirmed mempool transactions directly, which is the fastest
     path to "this happened minutes ago" data on Bitcoin.

3. UNIFIED SEARCH ENDPOINT: POST /api/v1/search accepting one raw string.
   Detect what it is before routing:
   - 0x + 40 hex chars -> EVM address
   - 0x + 64 hex chars -> EVM tx hash
   - T + 33 base58 chars -> TRON address
   - 64 hex chars, no 0x -> try TRON tx hash, then BTC tx hash
   - starts with 1 / 3 / bc1 -> BTC address
   If the input is a tx hash, resolve it to the relevant address(es) first
   (the "from" address for EVM/TRON; every output address for BTC — let the
   officer pick if there is more than one), open a new case/analysis run in
   the same action, and hand off to trace_engine. This must be a true
   one-box search, not a multi-step form.

4. FRESHNESS & CONFIRMATION HONESTY: every trace hop sourced from a live
   adapter must carry its confirmation count / pending status. Any hop with
   fewer than a configurable N confirmations (default 3) must be visibly
   flagged in both the evidence output and the UI as "low-confirmation,
   subject to reorg" — this is a forensic-accuracy requirement, not a UI
   nicety, and follows the project's existing never-overclaim principle.

5. CACHING & RATE-LIMIT RESILIENCE: add a short-TTL cache (an in-memory dict
   is fine for the demo) — 15-30s TTL for anything under N confirmations,
   longer for settled data. On a live API error or rate-limit response, serve
   the last cached result with a "data may be stale, retrying" flag rather
   than crashing or silently substituting fixture data without saying so.

6. FRONTEND: add one search bar in the app header, usable from any page,
   wired to /api/v1/search, showing a live status (searching -> found ->
   tracing -> done) rather than a blocking spinner, landing on the new case's
   GraphView once the trace completes.

Verification: with LIVE_MODE=true and a real EVM_RPC_URL + ETHERSCAN_API_KEY
set, search a real transaction hash from the last few minutes (use a small
test transaction, not live case data) and confirm the app returns a trace
within a few seconds, correctly flags any low-confirmation hop, and that
unsetting LIVE_MODE reverts the app to fixture-only behavior with zero
outbound calls — verify that with the network tab or a packet capture, not
just by reading the code.
```

### Phase 8B — Cross-Chain Bridge Detector & Streaming Graph Animation (only if time remains)

```
Using @PROJECT.md, add a scoped bridge_detector.py that only recognizes a
small, explicitly named list of bridge contracts with hand-written log
decoders for each (do not attempt general cross-chain resolution), and add a
WebSocket endpoint that streams trace_paths hop-by-hop as they're discovered
by the live or fixture adapter so the frontend graph can animate node/edge
creation live instead of rendering the finished graph all at once.
Verification: confirm the WebSocket stream renders correctly for both the
fixture scenarios and a live-mode search from Phase 8, and that the bridge
detector correctly no-ops (skips, doesn't crash) on any bridge contract not
in its named list.
```

### Phase 8C — Hotfix: Address Validation, Root-Entity Short-Circuit, Run-Status Integrity

```
Using @PROJECT.md, fix three specific bugs surfaced by testing Phase 8 with a
real address (34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo — a real Bitcoin P2SH address
that was misdetected as Ethereum):

1. REPLACE PREFIX-GUESSING WITH CHECKSUM VALIDATION. The current chain
   detection must not use loose prefix matching that can silently fall
   through to a default chain. Implement real validation per chain:
   - EVM: validate as 0x + 40 hex chars, and if mixed-case, validate the
     EIP-55 checksum (use eth-utils/web3.py's is_address / is_checksum_address
     rather than hand-rolled regex).
   - BTC: base58check-decode and validate the version byte (0x00 -> "1...",
     0x05 -> "3..."), or bech32-checksum-validate "bc1..." addresses. Reject
     anything that fails checksum rather than accepting it on prefix alone.
   - TRON: base58check-decode and validate TRON's version byte (0x41).
   If nothing validates, return UNRECOGNIZED_ADDRESS_FORMAT explicitly — never
   default to any chain silently.
   Audit every place the code calls .lower() or .upper() on an address. BTC
   base58 and TRON addresses, and checksummed EVM addresses, are
   case-sensitive — normalize casing only for an internal cache/lookup key,
   never for the value actually sent to a provider or shown to the officer.

2. ROOT-ADDRESS SELF-ATTRIBUTION SHORT-CIRCUIT. Before trace_engine runs,
   check the submitted root address itself against vasp_directory. If it
   matches a known hot/cold wallet, skip outward tracing entirely and return
   an immediate VERY_HIGH-confidence attribution with
   attribution_source="ROOT_ADDRESS_IS_KNOWN_ENTITY" and 0 hops needed by
   design — this must render in the UI as a clear "this address belongs to
   <Exchange>" state, not "insufficient evidence."

3. RUN-STATUS INTEGRITY. Replace the current binary complete/incomplete
   status with four distinct states, surfaced distinctly in both the API
   response and the UI badge (different color/text for each, not the same
   green pill for all):
   - ANALYSIS_COMPLETE_ATTRIBUTED (root match or trace found an off-ramp)
   - ANALYSIS_COMPLETE_NO_PATH_FOUND (adapter succeeded, genuinely no path)
   - ANALYSIS_FAILED_ADAPTER_ERROR (a live call errored/timed out)
   - ANALYSIS_FAILED_INVALID_ADDRESS (UNRECOGNIZED_ADDRESS_FORMAT from step 1)
   A failed run must never display as "Verified Complete."

Verification: re-run the search on 34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo and
confirm it is now detected as BTC (not ETH); seed it into vasp_directory as a
test fixture and confirm it now returns an immediate root-entity attribution
instead of "insufficient evidence" with 0 hops; separately submit a
deliberately garbage string and confirm it returns
ANALYSIS_FAILED_INVALID_ADDRESS with a distinct UI state, not the same green
badge as a real completed run.
```

### Phase 8D — Advanced: Sanctions Screening, Hub-Node Handling, Multi-Provider Resilience

```
Using @PROJECT.md, add three advanced capabilities on top of Phase 8/8C:

1. OFAC SDN SANCTIONS SCREENING. Add a sanctions_list table (address, chain,
   program, entity_name, source, last_updated). Populate it from the official
   OFAC SDN feed at
   https://www.treasury.gov/ofac/downloads/sanctions/1.0/sdn_advanced.xml,
   using the parsing approach from the open-source, MIT-licensed
   0xB10C/ofac-sanctioned-digital-currency-addresses project (github.com/
   0xB10C/ofac-sanctioned-digital-currency-addresses) as a reference for
   extracting per-chain address lists from that XML. Run this as a scheduled
   background job (nightly is sufficient) rather than fetching it per-request.
   Check both the root address and every hop's address against this table.
   A match must surface as its own explicit "OFAC SDN MATCH: <entity_name>"
   flag in the evidence output, kept distinct from ordinary VASP attribution
   since it carries independent legal significance.

2. HUB-NODE HANDLING FOR EFFICIENCY. Before trace_engine expands a node,
   check (or lazily probe) its transaction count. If it exceeds a
   configurable threshold (default 500), treat it as a probable
   service/hub — do not attempt to pull or expand its full history. Mark it
   in the trace output as HUB_NODE_NOT_EXPANDED with its tx count, rather
   than silently truncating or hanging on a huge exchange wallet.

3. PARALLEL, MULTI-PROVIDER LIVE QUERYING. When LIVE_MODE is on, issue the
   RPC call, the explorer REST call, and the sanctions-list check
   concurrently (asyncio.gather) with a per-call timeout, instead of
   sequentially. For each chain, support a fallback provider order (e.g. EVM:
   primary RPC -> public fallback RPC -> Etherscan REST) so one rate-limited
   provider doesn't stall the whole search.

Verification: confirm a search against a known OFAC-listed test address (use
one of the publicly listed SDN addresses, not a real case) correctly surfaces
the OFAC SDN MATCH flag; confirm searching the same large cold-wallet address
from Phase 8C now returns quickly with a HUB_NODE_NOT_EXPANDED flag instead of
attempting to pull its full transaction history; and confirm temporarily
breaking the primary EVM RPC URL causes the search to fall back to the
secondary provider rather than failing outright.
```

### Phase 8E — General-Purpose Worldwide Label Coverage (GraphSense TagPacks + Live Entity Fallback)

```
Using @PROJECT.md, replace the hand-seeded vasp_directory approach with a real,
broad, continuously-refreshable entity-attribution dataset. This phase makes
attribution work on addresses no one on the team manually entered — that is
the explicit goal, and verification below must prove it on addresses not
seeded by hand.

1. BULK-INGEST GRAPHSENSE TAGPACKS. Write an ingestion script that pulls the
   public, MIT-licensed TagPacks collection from
   github.com/graphsense/graphsense-tagpacks (YAML files under packs/) and
   loads them into a new entity_labels table: address, chain, label, actor_id,
   source_url, last_modified, tag_source='GRAPHSENSE_TAGPACK'. This is real
   labeled data for real exchanges, mixers, and services — not a demo seed.
   Also ingest the companion ActorPacks (organization metadata: label,
   categories such as exchange / mixer / darknet_market / defi) into an
   entities table linked via actor_id, so attribution carries a category, not
   just a name — feed this category into typology.py and risk_engine.py.

2. LIVE ENTITY FALLBACK. When an address (root or hop) is NOT found in the
   locally ingested entity_labels table and LIVE_MODE is on, query the public
   GraphSense hosted API (https://api.ikna.io — reference the graphsense-python
   client's endpoint patterns: GET /{currency}/addresses/{address}/entity and
   GET /{currency}/addresses/{address}/neighbors) for a real-time entity/
   cluster lookup. Apply the same caching, timeout, and fallback discipline as
   the other live adapters from Phase 8. Before relying on this in a live
   demo, confirm api.ikna.io's current usage terms/rate limits — treat it as
   a best-effort supplementary source. The locally ingested TagPack dataset
   must remain the primary, always-available path so air-gapped/LIVE_MODE=false
   deployments still have real (if less current) label coverage.

3. UPDATE ATTRIBUTION ORDER. attribution.py should now check, in this order,
   and report which one fired: (a) local entity_labels match, (b) live
   GraphSense entity API match if LIVE_MODE is on, (c) OFAC sanctions match
   (Phase 8D), (d) CEX sweep-heuristic match (Phase 4). Each must produce a
   distinct, visible rule_fired value — an officer should be able to tell a
   "known from our local dataset" attribution apart from a "matched via live
   lookup" one.

4. SCHEDULED REFRESH. Add a periodic job (weekly is reasonable) that re-pulls
   the latest TagPacks/ActorPacks and upserts entity_labels/entities, so
   coverage grows over time instead of being a fixed snapshot from setup day.

Verification: run the ingestion script and confirm entity_labels has real
exchange/service entries pulled from the actual TagPacks repository, not
manually typed ones. Pick two or three addresses directly from that dataset
that nobody on this project entered by hand, search them, and confirm each
returns a genuine local-dataset attribution with the correct entity name and
category. Then pick an address deliberately absent from the local dataset,
confirm it falls through to the live GraphSense API when LIVE_MODE is on and
returns a clean "no match found locally or live" result when LIVE_MODE is
off — proving the system is not special-cased to any single address.
```

### Phase 9 — Hardening & Deployment

```
Using @PROJECT.md, run through: expand pytest coverage for edge cases
(empty trace, malformed address, hop-budget exhaustion), add rate-limiting
to public-facing endpoints, review that no route bypasses RBAC/RLS, confirm
.env.example has no real secrets committed anywhere in git history, and
finalize docker-compose.yml for a single `docker compose up --build`
production-shaped deployment with Nginx as the entry point. Write a short
DEPLOYMENT.md covering both the offline/air-gapped mode (FixtureAdapter only,
no outbound calls) and the connected mode (live adapters + API keys).
Verification: a clean `git clone` + `docker compose up --build` on a machine
with no prior state reaches a working login screen with zero manual steps
beyond copying .env.example to .env.
```

---

## 3. Feeding Instructions

Read this before you paste anything above into Antigravity.

1. **Save the Master Context Block (§0) into the repo as `PROJECT.md` on day one**, and reference it with `@PROJECT.md` in every phase prompt (Antigravity's `@`-path picker will pull it in). Don't retype the context each time — that's what the file is for.

2. **One phase per paste, in order.** Don't jump ahead to Phase 7's "wow" features before Phase 0-6 are demo-stable — a crashing stretch feature costs you more in finals than a missing one. If you're short on time, cut from the bottom of this list, not the middle.

3. **Use Planning mode for Phase 0 and Phase 1.** These set the shape everything else builds on — let Antigravity produce a plan, read it, and only then approve execution. For Phases 2 onward, once the architecture is settled, direct execution is fine if you trust the pattern it's established.

4. **Never paste real Supabase keys, API keys, or `.env` contents into the chat.** Reference them by variable name only (`SUPABASE_SERVICE_ROLE_KEY`, etc.) and let the agent read them from the actual `.env` file on disk via its file tools. If you're pasting credentials into a prompt box, stop and fix that first.

5. **Do not approve a phase until its stated verification step actually passes.** Watch the agent run the test/build/browser check itself — don't take "should work now" on faith. This is the single highest-leverage habit for agentic coding: a bad Phase 2 compounds into a much worse Phase 5.

6. **If the agent proposes something outside the current phase's stated scope** ("while I'm here, should I also add X?"), redirect it back to the phase as written. Scope creep mid-phase is how a 9-phase plan turns into an unfinished mess by hour 30.

7. **Attach screenshots for anything visual.** For Phase 6 and any graph-rendering work, if something looks wrong, copy the screenshot and paste it directly into the prompt box (Antigravity's agents can consult attached images to diagnose rendering issues) rather than trying to describe the bug in words.

8. **After each phase, skim the diff, not just the test output.** Tests passing doesn't mean the code is something you'd want to defend to a judge who reads it. You're the reviewer; the agent is the implementer.

9. **When you reach Phase 8 (multi-chain/live providers), get real API keys (e.g. a free-tier Etherscan/TronGrid key) before starting the phase**, not mid-phase — the agent will otherwise build against guessed response shapes.

10. **Keep this file updated as the source of truth.** If you deviate from a phase while building (you will), add a line to that phase's block noting the deviation, so the next phase's prompt — and the next person reading this repo — isn't working from a stale plan.