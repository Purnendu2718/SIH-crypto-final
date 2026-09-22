# CryptoTrace Sentinel (SIH26183) — Project Status

## Status: Phase 7 Complete

### Overview
CryptoTrace Sentinel is an open-source, self-hostable blockchain-forensics platform for Indian law enforcement. It takes a victim-reported crypto wallet address, traces fund flow across multi-hop transactions, attributes receiving exchanges/VASPs with explainable confidence scores, detects laundering typologies, and produces court-ready evidence packages along with pre-drafted Section 94 BNSS statutory requisition notices and Section 63 BSA electronic record certificates.

---

### Phase History & Implementation Status

- **Phase 0 — Repo Scaffolding**: Completed. FastAPI backend skeleton, Vite + React + Tailwind frontend skeleton, Docker Compose, root `.env.example`, Makefile.
- **Phase 1 — Officer Auth Portal & RBAC**: Completed. Supabase JWT auth, PBKDF2/bcrypt fallback, profiles table with roles (`INVESTIGATOR`, `SUPERVISOR`, `ADMIN`), caseload preloading, RLS.
- **Phase 2 — Domain Models, Chain Adapters, Fixtures**: Completed. SQLAlchemy models, `FixtureAdapter` with 4 realistic forensic scenarios (swept exchange hot wallet, fan-out mixer, cross-chain bridge hop, weakly connected path), VASP directory seeded.
- **Phase 3 — Multi-Chain Search & Validation**: Completed. Address and transaction hash validation across ETH, BTC, TRON, and multi-chain explorer lookup with demo dataset fallbacks.
- **Phase 4 — Attribution, Risk, Typology & Taint Engines**: Completed. Weighted scoring attribution model (sweep/label match 0.35, proximity 0.20, deposit similarity 0.15, temporal 0.15, co-spend 0.10, behavioral 0.05), confidence bands (`VERY_HIGH`, `HIGH`, `MEDIUM`, `INSUFFICIENT_EVIDENCE`), rule detectors for `FAN_OUT`, `MIXER`, `PEELING_CHAIN`, `LAYERING`, FIFO taint contamination engine, composite 0-100 risk scoring.
- **Phase 5 — Evidence, Audit Log, Legal Notice, PDF Report**: Completed. SHA-256 evidence package hashing with Merkle roots, append-only hash-chained audit log with integrity verification, Section 94 BNSS requisition notice generation with nodal contacts, ReportLab PDF evidence report generator.
- **Phase 6 — Frontend: Login, Cases, and Trace Graph**: Completed.
  - **Auth & API Client**: In-memory token management with `sessionStorage` fallback, automatic `Authorization: Bearer` injection, `@microsoft/fetch-event-source` for SSE streaming, role-based route guard (`ProtectedRoute`), role-aware UI navigation.
  - **Dev Proxy & Config**: Vite proxy for `/api` targeting `http://localhost:8000`, using `import.meta.env.VITE_API_URL`. Updated search page to attach Bearer token.
  - **Case Management**: Cases list with immediate caseload preload, Case detail with addresses, traces, and disabled tabs for `evidence`, `legal`, `notices`, `alerts` displaying "coming next".
  - **Trace Form**: Seed address, hops (1-6), min amount filter, date range, taint model selector (FIFO, Proportionate, Highest First), live progress via SSE.
  - **Cytoscape Graph Visualization (`cytoscape-dagre`)**:
    - Node size scaled by cumulative value.
    - Color coding: Exchange (Amber), Mixer (Purple), Sanctioned (Red), Unlabelled (Slate), Lead (Rose), Bridge (Cyan).
    - Edge width scaled by taint percentage (2px - 8px).
    - Edge heuristic badges (`SWEEP`, `FAN_OUT`, `MIXER`, `BRIDGE`, `LOW_CONF`).
    - Cycles detected and highlighted in crimson with dashed animated edges.
    - Endpoints outlined with high-contrast rings.
    - Time filter slider, legend, full-screen canvas controls.
    - Interactive node side panel: address, labels with confidence/source, first/last seen timestamps, direct links to public blockchain explorers, instant copy button.
    - Performance guard: Automatically collapses low-value leaves when total graph nodes exceed 1,500.
  - **Terminology Compliance**:
    - Prominently displays "Attribution is not proof" beside attribution labels.
    - Strictly enforces words "lead" and "flagged address" across all user-facing UI; forbidden word "suspect" eliminated.
  - **Export**: Export active graph visualization as high-resolution PNG (`cy.png()`) and raw Cytoscape JSON (`cy.json()`).
  - **Accessibility (a11y)**:
    - Full keyboard navigation (Tab, Enter, Escape) for side panel and controls.
    - ARIA attributes (`aria-label`, `role="dialog"`, `aria-modal="true"`).
    - Sufficient contrast meeting WCAG AA standards in dark theme.
    - Text alternative summary modal providing complete tabular and textual representation of node counts, category distribution, identified endpoints, and detected cycles.
  - **i18n & Localization**:
    - `i18next` with `react-i18next` configured for English (`en`) and Hindi (`hi`).
    - Language switcher toggle in the shell header.
    - **Notice**: All Hindi (`hi`) strings in `frontend/src/lib/i18n.ts` are machine-translated and require human review by native Hindi-speaking law enforcement subject matter experts.
  - **Automated Tests**: Vitest unit tests for graph transform, API client, route guard; build & type-check passing.
- **Phase 7 — Evidence Package, Report and Integrity Verification**: Completed.
  - **Evidence Package Endpoint**: `GET /api/v1/cases/{id}/evidence-package` (investigator role, RLS enforced) generates and exports a complete ZIP package saved under `EXPORT_DIR` (`./data/exports`).
  - **Package Contents**:
    - `report.pdf`: Pure Python ReportLab forensic report with case header, methods & limitations (heuristics glossary, taint assumptions, "Attribution is not proof"), trace parameters, summary of endpoints and circular cycles, table of key transfers with txids, label table with confidence and sources, and appendix with SHA-256 evidence hashes where every claim references an artifact ID.
    - `certificate_draft.pdf`: Section 63 Bharatiya Sakshya Adhiniyam, 2023 (BSA 2023) electronic record certificate draft, stamped on every page with `"DRAFT - for review by legal counsel; verify the prescribed Schedule format before use"`, with placeholders for the person in charge and a forensic expert.
    - `graph.json`: Serialized multi-hop graph topology state.
    - `artifacts/`: Directory containing raw provider responses and snapshots (`raw_trace_payload.json`, `raw_transactions.json`, `vasp_directory_snapshot.json`, `case_metadata.json`).
    - `MANIFEST.json`: Cryptographic manifest detailing every file with SHA-256 digest, byte size, scrubbed source URL without API keys, fetched_at timestamp, engine version, and parameters.
    - `audit_excerpt.json`: Cryptographic hash-chained audit log excerpt covering case actions with `prev_hash` and `entry_hash`.
    - `verify.py`: Standalone, standard-library-only Python verification script.
    - `README.txt`: Independent court verification and defensibility guide.
    - `MANIFEST.tsr` (optional): RFC 3161 trusted timestamp token if `TSA_URL` is set; if unset, the report states `"not externally anchored"`.
  - **Defensible Tamper-Evident Verification**:
    - `verify.py` passes on clean packages.
    - Detects and halts on single-byte corruption in any artifact.
    - Detects and halts on audit log row or hash chain tampering.
  - **Audit Logging**: Export action recorded as `EVIDENCE_PACKAGE_EXPORTED` in the database audit log.
  - **Automated Tests**: Pytest test suite (`test_phase7_evidence_package.py`) with 8 tests covering packaging, verification, single-byte tamper detection, certificate stamping, and audit logging.

---

### Verification Checklist
Run `python scripts/check.py` to run all test suites across backend (124 pytest tests) and frontend (28 vitest tests + production build).
