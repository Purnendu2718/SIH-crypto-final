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

- **Phase 9 — Complaint Intake with Guarded Extraction**: Completed.
  - **LLM Abstraction (`app/llm/`)**:
    - Providers: `none` (default deterministic), `anthropic`, and `ollama` implemented using `httpx` exclusively (no third-party SDK dependencies).
    - Model dynamically configured via `LLM_MODEL`; provider credentials from environment variables (`ANTHROPIC_API_KEY`, `OLLAMA_URL`). No hard-coded model names.
    - Provider `none` operates fully offline in deterministic mode and explicitly communicates this state.
  - **Deterministic Identifier & Near-Miss Extraction**:
    - Scans unformatted complaints for candidate tokens (25-110 characters, 0x-prefixed hex, 64-hex hashes).
    - Validates each candidate using `address_validator.validate()`, returning chain candidates, network, address type, and certainty.
    - Detects near-miss typos (e.g. 0/O confusion, transposed characters, truncated hex) returning validator `error` and actionable `hint` for investigating officers.
  - **Guarded AI Extraction & Substring Containment Guard**:
    - Extracts structured facts: offence date, amounts & currency, victim loss in INR, exchange/bank/UPI entities, typology suggestion (constrained to Phase 8 enum), English translation, and neutral summary.
    - Enforces Pydantic schema validation with one automated retry on parse/validation errors.
    - Evidentiary containment: Every extracted fact requires an `evidence_quote`. Substring verification normalizes text using Unicode NFKC and collapsed whitespace; facts failing exact containment are preserved in `rejected_facts` with specific rejection reasons rather than being silently dropped.
  - **DPDP Act, 2023 Compliance & PII Redaction (`app/services/pii_masker.py`)**:
    - Automated detection and redaction of Indian Personal Identifiable Information: Indian mobile numbers (`[PHONE_REDACTED]`), 12-digit Aadhaar numbers (`[AADHAAR_REDACTED]`), PAN cards (`[PAN_REDACTED]`), and Bank Account numbers (`[ACCOUNT_REDACTED]`).
    - PII is masked before passing to external AI prompts or system logs. Original complaint text is stored strictly within the secure database (`complaint_intakes.original_text`) per DPDP 2023 Section 8(4) evidentiary retention provisions, and is never emitted to application logs.
  - **REST API Endpoints (`app/routers/intake.py`)**:
    - `POST /api/v1/intake`: Processes complaint, redacts PII, executes extraction, and appends `COMPLAINT_INTAKE_PROCESSED` to the hash-chained audit log.
    - `POST /api/v1/intake/{id}/create-case`: Provisions a new case with linked wallet submissions and analysis runs from accepted addresses, appending `CASE_CREATED_FROM_INTAKE` to the audit log.
  - **Investigator UI (`frontend/src/pages/IntakePage.tsx`)**:
    - Dedicated Intake page with large complaint input, multilingual sample presets (English, Hindi), DPDP statutory notice, deterministic operation banner, 3-group results display (accepted addresses, near-misses with hints, verified facts with highlighted quotes), and one-click case creation.
  - **Automated Tests (`backend/tests/test_phase9_intake.py`)**:
    - 11 pytest test cases covering Hindi & English address extraction, near-miss hint diagnosis, quote verification rejecting fabricated facts, PII masking, provider `none`, provider error degradation, and end-to-end API case creation with audit logs.

---

### Verification Checklist
Run `python scripts/check.py` to run all test suites across backend (151 pytest tests), address validator (29 unittests), and frontend (28 vitest tests + production build).

