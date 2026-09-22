# CryptoTrace Sentinel (SIH26183) — Project Status

## Status: Phase 8 Complete

### Overview
CryptoTrace Sentinel is an open-source, self-hostable blockchain-forensics platform for Indian law enforcement. It takes a victim-reported crypto wallet address, traces fund flow across multi-hop transactions, attributes receiving exchanges/VASPs with explainable confidence scores, detects laundering typologies, and produces court-ready evidence packages along with pre-drafted Section 94 BNSS statutory requisition notices, Section 63 BSA electronic record certificates, and deterministic legal statutory suggestions (BNS, BNSS, IT Act, PMLA).

---

### Phase History & Implementation Status

- **Phase 0 — Repo Scaffolding**: Completed.
- **Phase 1 — Officer Auth Portal & RBAC**: Completed.
- **Phase 2 — Domain Models, Chain Adapters, Fixtures**: Completed.
- **Phase 3 — Multi-Chain Search & Validation**: Completed.
- **Phase 4 — Attribution, Risk, Typology & Taint Engines**: Completed.
- **Phase 5 — Evidence, Audit Log, Legal Notice, PDF Report**: Completed.
- **Phase 6 — Frontend: Login, Cases, and Trace Graph**: Completed.
- **Phase 7 — Evidence Package, Report and Integrity Verification**: Completed.
- **Phase 8 — Legal Mapping Engine (BNS, BNSS, IT Act, PMLA)**: Completed.
  - **Statutory Rules Definition (`app/legal/rules.yaml`)**:
    - Closed initial provision table of 13 sections strictly defined: BNS 318(4) [IPC 420], BNS 316 [IPC 406], BNS 61 [IPC 120B], BNS 303 [IPC 378/379] marked `verified: true`; BNS 308 [IPC 383/384], BNS 351 [IPC 503/506], BNS 319 [IPC 416/419], BNS 317 [IPC 410/411], BNS 111, IT Act 2000 s.43 & s.66, s.66C, s.66D, PMLA 2002 s.3 & s.4 marked `verified: false`.
    - Every provision links to `https://indiacode.nic.in`.
    - 7 typologies mapped: `investment_scam`, `phishing_impersonation`, `hack_theft`, `ransomware_extortion`, `sextortion`, `insider_misappropriation`, `layering_laundering`.
    - Ingredients checklists for each typology with sources (`complaint`, `on_chain`, `officer`) and signals (`cycle_detected`, `multi_hop_layering`, `mixer_exposure`, `sanctioned_exposure`, `exchange_endpoint`, `peel_chain`).
  - **Deterministic Rules Engine (`app/legal/engine.py`)**:
    - Strict schema validation fails on malformed or invalid YAML.
    - Offence date switch at the `2024-07-01` boundary: dates prior to 1 July 2024 return IPC equivalents as primary; dates on/after 1 July 2024 return BNS as primary; missing dates return both schemes with an advisory note.
    - Signal evaluator deriving on-chain ingredients from case trace data, including cycle loop detection.
  - **API Endpoint (`backend/app/routers/legal.py`)**:
    - `POST /api/v1/cases/{id}/legal-suggestions` and `POST /api/cases/{id}/legal-suggestions` with RLS clearance.
    - Responses include `rules_version`, mandatory disclaimer (`"Suggestions for review by the investigating officer and legal counsel; verify each section on indiacode.nic.in."`), and strict badges (`"Cross-checked"` / `"Unverified"`, never officially confirmed).
  - **Frontend UI (`frontend/src/components/LegalSuggestionsComponent.tsx` & `CaseDetail.tsx`)**:
    - Dedicated "Legal Provisions" tab on the Case page.
    - Typology selector, date picker with 2024-07-01 switch note, provision cards with India Code links and comparison table badges, ingredients checklist with status pills, and copy-to-clipboard case diary summary.
  - **Automated Tests**:
    - Pytest suite `backend/tests/test_phase8_legal_engine.py` (16 tests) covering date switch boundary, cycle checklist evaluation, YAML validation failures, and mandatory disclaimers.

---

### Verification Checklist
Run `python scripts/check.py` to run all test suites across backend (140 pytest tests) and frontend (28 vitest tests + production build).

