# CryptoTrace Sentinel (SIH26183) — Project Status

## Status: Phase 6 Complete

### Overview
CryptoTrace Sentinel is an open-source, self-hostable blockchain-forensics platform for Indian law enforcement. It takes a victim-reported crypto wallet address, traces fund flow across multi-hop transactions, attributes receiving exchanges/VASPs with explainable confidence scores, detects laundering typologies, and produces court-ready evidence packages along with pre-drafted Section 94 BNSS statutory requisition notices.

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
  - **Automated Tests**:
    - Unit tests for graph-data transformation engine (`calculateNodeSize`, `calculateEdgeWidth`, `determineCategory`, `detectCycles`, `transformTraceToGraph`, endpoints, performance collapse guard).
    - Unit tests for API client (token in-memory, sessionStorage restore, request header injection).
    - Unit tests for route guard and RBAC role checks (`ProtectedRoute`).
    - Full TypeScript type-checking and production build verification (`npm run build`).

---

### Verification Checklist
Run `python scripts/check.py` to run all test suites across backend and frontend.
