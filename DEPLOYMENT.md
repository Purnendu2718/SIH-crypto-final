# CryptoTrace Sentinel (SIH26183) — Deployment & Hosting Guide

An open-source, self-hostable blockchain-forensics platform for Indian Law Enforcement Agencies (MHA / I4C).

---

## 1. Production Deployment: Zero-Touch Docker Compose & Nginx

For production servers, workstations, and law enforcement forensics labs. A clean checkout requires **zero manual database or seeding steps** beyond copying `.env.example`.

### Architecture
- **Nginx (Port 80)**: Single entry point reverse proxy routing `/` to the frontend, `/api/` to the FastAPI backend, and `/api/ws/` for real-time WebSocket trace streaming.
- **Backend (Port 8000)**: FastAPI service executing the forensic pipeline, FIFO taint accounting, typology detection, and PDF generation.
- **Frontend (Port 5173)**: React 18 + Vite interface with Cytoscape.js interactive graph canvas.
- **Database (Port 5432)**: PostgreSQL 15 container with persistent volume storage (`pgdata`).

### Single-Command Launch
```bash
# 1. Copy environment template
cp .env.example .env

# 2. Build and launch all services
docker compose up --build -d
```

### Access URLs
- **Web Application Portal**: [http://localhost](http://localhost) (via Nginx reverse proxy on port 80)
- **API Documentation (Swagger)**: [http://localhost/docs](http://localhost/docs)
- **API Health Check**: [http://localhost/api/health](http://localhost/api/health)
- **WebSocket Streaming**: `ws://localhost/api/ws/trace/{submission_id}`

### Pre-Seeded Officer Credentials
On first boot, the backend automatically initializes the schema, creates demo cases, seeds VASP hot-wallets, and provisions officer accounts with zero manual action:
| Role | Email | Password | Clearance Scope |
| :--- | :--- | :--- | :--- |
| **Investigator** | `sharma@sentinel.gov.in` | `SentinelPass123!` | Delhi Cyber Cell (assigned cases only) |
| **Investigator** | `patel@sentinel.gov.in` | `SentinelPass123!` | Mumbai Cyber Cell (assigned cases only) |
| **Supervisor** | `verma@sentinel.gov.in` | `SentinelPass123!` | I4C Coordination HQ (all department cases) |
| **Administrator** | `hq.admin@sentinel.gov.in` | `AdminPass123!` | National Cyber Crime Portal HQ (full system) |

---

## 2. Operational Deployment Modes

### Mode A: Air-Gapped / Offline Forensic Lab Mode (`LIVE_MODE=false`, Default)
Designed for secure, classified, or air-gapped forensic environments without internet connectivity:
- **Chain Adapters**: Operates 100% on deterministic, pre-verified forensic scenarios and VASP hot-wallet registries via `FixtureAdapter`.
- **Entity Attribution**: Primary resolution relies on the locally bundled **GraphSense TagPacks** seed (`tagpacks_seed.json`), covering over 3,800 actors and 9,000 real-world labels offline.
- **Zero Outbound Calls**: No external HTTP requests are made to blockchain explorers, public RPC nodes, or external hosted APIs.
- **Court Evidence Generation**: Generates cryptographically verifiable Section 63 BSA / 94 BNSS court-ready PDF evidence packages locally via ReportLab.
- **Deterministic Typology Detection**: Identifies mixers, peeling chains, fan-outs, and DeFi DEX interactions using local transaction graphs.

### Mode B: Connected Mode (`LIVE_MODE=true`, Active Intelligence)
Enables live multi-chain scanning and dynamic GraphSense cluster resolution:
- **Multi-Chain Adapters**: Queries live RPC and explorer APIs for Ethereum, TRON, and Bitcoin networks.
- **Live GraphSense Fallback**: When an address is absent from local TagPacks, queries the public hosted GraphSense API (`https://api.ikna.io`) with strict 5.0s timeouts and short-TTL caching.
- **Mempool & Freshness Tracking**: Real-time confirmation tracking and low-confirmation reorg warnings via mempool.space.
- **Configuration (`.env`)**:
  ```env
  LIVE_MODE=true

  # EVM (Ethereum / Polygon / Arbitrum)
  EVM_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
  ETHERSCAN_API_KEY=YOUR_ETHERSCAN_KEY

  # TRON Network
  TRON_RPC_URL=https://api.trongrid.io
  TRONGRID_API_KEY=YOUR_TRONGRID_KEY

  # Bitcoin Mempool
  MEMPOOL_API_URL=https://mempool.space/api

  # GraphSense Hosted Entity API
  GRAPHSENSE_API_URL=https://api.ikna.io
  GRAPHSENSE_API_KEY=

  # Telegram Golden Hour Alerts (Optional)
  ENABLE_TELEGRAM_WEBHOOK=false
  TELEGRAM_BOT_TOKEN=
  TELEGRAM_CHAT_ID=

  # AI Co-pilot (Optional)
  GEMINI_API_KEY=
  ```

---

## 3. Security, Hardening & Statutory Governance

### Public Endpoint Rate Limiting
- **In-Memory Sliding-Window Limiter**: Protects auth and search routes against credential stuffing, brute force, and scraping DoS.
- **Tiers**:
  - `/api/auth/login` and `/api/auth/signup`: **10 requests / minute per IP**.
  - `/api/v1/search` and `/api/analysis/quick-trace`: **30 requests / minute per IP**.
  - Global default: **120 requests / minute per IP**.
- **Response**: Exceeded limits return `HTTP 429 Too Many Requests` with `Retry-After` header and `X-RateLimit-*` counters.

### Strict RBAC & Row-Level Security (RLS)
- **Investigator Isolation**: Investigators are strictly constrained to cases assigned to their officer ID (`assigned_officer_id == auth.uid()`).
- **Cross-Case Boundary Protection**: Investigators cannot inspect, trace, generate evidence for, or download PDFs from cases assigned to other officers.
- **Supervisor & Admin Clearance**: Supervisors and administrators possess departmental oversight across all officer caseloads.
- **Role Escalation Protection**: Public API role promotion is blocked in production mode; promotions require the administrative CLI tool (`python scripts/promote_officer.py`).

### Statutory Legal Admissibility
- **Section 63 Bharatiya Sakshya Adhiniyam (BSA), 2023**: Generates signed cryptographic evidence certificates containing SHA-256 package hashes and Merkle root leaf proofs.
- **Section 94 Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023**: Pre-drafts statutory notice requisitions with exchange compliance nodal contacts.
- **Tamper-Evident Audit Log**: Hash-chained block integrity log tracks every case access, evidence export, and search action.

---

## 4. Native Local Development (No Docker)

```bash
# Terminal 1: Backend
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2: Frontend
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```
On Windows, run `host.bat` or `.\host.ps1` to launch both services in a single step.

---

## 5. Verification Checklist

Run the automated test suite to confirm complete compliance across all 9 phases:
```bash
cd backend
pytest -v
```
All **76 tests** must pass with 0 failures, covering:
- Phase 1–6 Core: BFS tracing, attribution scoring, typology detection, FIFO taint accounting, Merkle proofs, Section 94 BNSS notice, RBAC isolation.
- Phase 7 Innovations: UPI-UTR correlation, Golden Hour monitoring, Police Intel exchange, Arjuna bilingual co-pilot.
- Phase 8/8C/8E Live: EVM/TRON/BTC live adapters, bridge hop detection, OFAC sanctions matching, GraphSense TagPacks ingestion, live entity fallback.
- Phase 9 Hardening: Empty traces, malformed/injection addresses, hop budget exhaustion, burn addresses, dust thresholds, rate limiting, and cross-officer RLS isolation.

