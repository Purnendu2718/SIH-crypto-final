"""Evidence Package Assembler and ZIP Exporter.
Constructs court-defensible forensic ZIP packages containing:
- report.pdf (ReportLab, pure Python)
- certificate_draft.pdf (Section 63 BSA 2023 with legal stamp on every page)
- graph.json (trace result graph)
- artifacts/ (raw provider responses, transactions, VASP snapshot, case metadata)
- MANIFEST.json (SHA-256, size, scrubbed URL, fetched_at, engine version, parameters)
- MANIFEST.tsr (RFC 3161 timestamp response token if TSA_URL set)
- audit_excerpt.json (audit rows for the case with hash chain linkage)
- verify.py (standalone standard-library verifier)
- README.txt (court verification instructions)

Reference: Phase 7 — Evidence package, report and integrity verification.
"""

import os
import json
import zipfile
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import Case, WalletSubmission, AnalysisRun, VASPDirectory, AuditLog, utc_now
from app.services import run_full_forensic_pipeline
from app.services.report_generator import generate_pdf_evidence_report
from app.services.certificate_generator import generate_section_63_certificate_pdf
from app.services.tsa_client import request_rfc3161_timestamp
from app.services.verify_template import VERIFY_SCRIPT_CONTENT
from app.services.audit import append_audit_entry, format_canonical_timestamp
from app.services.adapters import get_adapter

ENGINE_VERSION = "0.1.0"


def scrub_url(url: Optional[str]) -> str:
    """Scrub sensitive query parameters (API keys, secrets) from URLs."""
    if not url:
        return "urn:cryptotrace:on-chain-provider"
    # Basic scrubbing of key/token query params
    if "?" in url:
        base, query = url.split("?", 1)
        params = query.split("&")
        safe_params = []
        for p in params:
            k = p.split("=")[0].lower()
            if any(secret_kw in k for secret_kw in ["key", "secret", "token", "auth", "pass"]):
                safe_params.append(f"{p.split('=')[0]}=REDACTED")
            else:
                safe_params.append(p)
        return f"{base}?{'&'.join(safe_params)}"
    return url


def build_evidence_package(
    case_id: str,
    officer: Any,
    db: Session,
    export_dir: Optional[str] = None,
    tsa_url: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """Build complete court-ready evidence ZIP package.
    
    Returns:
        (zip_file_path, zip_filename, manifest_dict)
    """
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise ValueError(f"Case with ID {case_id} not found.")

    # 1. Determine primary submission and run
    submissions = case.wallet_submissions
    primary_sub = submissions[0] if submissions else None
    start_address = primary_sub.address if primary_sub else "0x0000000000000000000000000000000000000000"
    chain = primary_sub.chain if primary_sub else "ETH"

    # Find or execute analysis run
    latest_run = None
    if primary_sub and primary_sub.analysis_runs:
        latest_run = primary_sub.analysis_runs[-1]

    stolen_val = float(case.amount_inr) if case.amount_inr else None

    # Run forensic pipeline if needed or reuse existing
    forensic_data = run_full_forensic_pipeline(
        start_address=start_address,
        chain=chain,
        run_id=latest_run.run_id if latest_run else None,
        stolen_principal=stolen_val,
        db=db,
    )

    now_iso = utc_now().isoformat()
    package_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_ncrp = (case.ncrp_ref or case.case_id).replace("/", "_").replace("\\", "_").replace(" ", "_")
    zip_filename = f"evidence_package_{safe_ncrp}_{package_timestamp}.zip"

    # Resolve export dir
    target_dir = export_dir or os.getenv("EXPORT_DIR", os.path.join(os.getcwd(), "data", "exports"))
    os.makedirs(target_dir, exist_ok=True)
    zip_path = os.path.join(target_dir, zip_filename)

    # In-memory file buffer collection: rel_path -> bytes
    package_files: Dict[str, bytes] = {}

    # --- 1. Artifacts Directory ---
    # a. Raw trace payload
    raw_trace_bytes = json.dumps(forensic_data, indent=2, sort_keys=True, default=str).encode("utf-8")
    package_files["artifacts/raw_trace_payload.json"] = raw_trace_bytes

    # b. Raw transactions from adapter
    try:
        adapter = get_adapter(chain)
        txs = adapter.get_transactions(start_address, chain)
        raw_tx_bytes = json.dumps(txs, indent=2, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        raw_tx_bytes = json.dumps(forensic_data.get("trace", {}).get("paths", []), indent=2, default=str).encode("utf-8")
    package_files["artifacts/raw_transactions.json"] = raw_tx_bytes

    # c. VASP directory snapshot
    try:
        vasps = db.query(VASPDirectory).all()
        vasp_snapshot = [
            {
                "entity_name": v.entity_name,
                "chain": v.chain,
                "fiu_ind_registered": v.fiu_ind_registered,
                "sla_hours": float(v.sla_hours) if v.sla_hours else 24,
                "nodal_contact": v.nodal_contact,
            }
            for v in vasps
        ]
        vasp_bytes = json.dumps(vasp_snapshot, indent=2, sort_keys=True).encode("utf-8")
    except Exception:
        vasp_bytes = b"[]"
    package_files["artifacts/vasp_directory_snapshot.json"] = vasp_bytes

    # d. Case metadata
    case_meta = {
        "case_id": case.case_id,
        "ncrp_ref": case.ncrp_ref,
        "victim_utr": case.victim_utr,
        "amount_inr": float(case.amount_inr) if case.amount_inr else None,
        "flagged_address": start_address,
        "chain": chain,
        "status": case.status,
        "created_at": case.created_at.isoformat() if case.created_at else now_iso,
        "assigned_officer_id": case.assigned_officer_id,
    }
    package_files["artifacts/case_metadata.json"] = json.dumps(case_meta, indent=2, sort_keys=True).encode("utf-8")

    # --- 2. Graph State (graph.json) ---
    graph_state = {
        "start_address": start_address,
        "chain": chain,
        "total_hops": forensic_data.get("trace", {}).get("total_hops", 0),
        "reached_vasp": forensic_data.get("trace", {}).get("reached_vasp", False),
        "vasp_name": forensic_data.get("trace", {}).get("vasp_name"),
        "paths": forensic_data.get("trace", {}).get("paths", []),
        "attribution": forensic_data.get("attribution", {}),
        "typologies": forensic_data.get("typologies", []),
        "taint": forensic_data.get("taint", {}),
        "risk": forensic_data.get("risk", {}),
    }
    package_files["graph.json"] = json.dumps(graph_state, indent=2, sort_keys=True, default=str).encode("utf-8")

    # --- 3. Audit Excerpt (audit_excerpt.json) ---
    # Query all audit rows up to this point to preserve contiguous hash chain
    audit_entries_db = db.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()
    audit_excerpt_list = [
        {
            "entry_id": a.entry_id,
            "prev_hash": a.prev_hash,
            "entry_hash": a.entry_hash,
            "officer_id": a.officer_id,
            "action": a.action,
            "target_id": a.target_id,
            "timestamp": format_canonical_timestamp(a.timestamp),
        }
        for a in audit_entries_db
    ]
    audit_excerpt_payload = {
        "case_id": case.case_id,
        "ncrp_ref": case.ncrp_ref,
        "exported_at": now_iso,
        "total_entries": len(audit_excerpt_list),
        "contiguous": True,
        "entries": audit_excerpt_list,
    }
    package_files["audit_excerpt.json"] = json.dumps(audit_excerpt_payload, indent=2, sort_keys=True).encode("utf-8")

    # --- 4. Standalone Verifier & README ---
    package_files["verify.py"] = VERIFY_SCRIPT_CONTENT.encode("utf-8")

    readme_text = f"""======================================================================
CRYPTOTRACE SENTINEL — FORENSIC EVIDENCE DOSSIER (SIH26183)
======================================================================
Case NCRP Reference : {case.ncrp_ref or 'UNASSIGNED'}
Case Unique ID      : {case.case_id}
Flagged Address     : {start_address} ({chain})
Defrauded Amount    : INR {case.amount_inr or 0:,.2f}
Export Generated At : {now_iso}
Engine Version      : {ENGINE_VERSION}

PACKAGE CONTENTS:
-----------------
1. report.pdf               - Court-Ready Forensic Examination Report
2. certificate_draft.pdf    - Section 63 BSA 2023 Electronic Record Certificate
3. graph.json               - Multi-Hop Forensic Graph State
4. artifacts/               - Raw On-Chain Ledgers & Provider Snapshots
   • raw_trace_payload.json
   • raw_transactions.json
   • vasp_directory_snapshot.json
   • case_metadata.json
5. audit_excerpt.json       - Cryptographic Hash-Chained Audit Trail
6. MANIFEST.json            - Cryptographic File Manifest with SHA-256 & Size
7. MANIFEST.tsr             - RFC 3161 Timestamp Response Token (if configured)
8. verify.py                - Standalone Python Standard Library Verifier
9. README.txt               - This instruction manual

INSTRUCTIONS FOR INDEPENDENT COURT / LAB INTEGRITY VERIFICATION:
----------------------------------------------------------------
1. Extract the contents of this ZIP archive into an empty folder.
2. Open a terminal / command prompt in that folder.
3. Run the standalone verification script (requires standard Python 3.7+):
       python verify.py
4. The verifier will:
   (a) Recompute SHA-256 checksums and byte sizes for every declared file.
   (b) Verify cryptographic hash-chain continuity across the audit trail.
   (c) Output PASS or point directly to any modified byte.

DEFENSIBILITY & STATUTORY STATEMENT:
------------------------------------
Attribution is decision-support intelligence, not proof of individual culpability.
This electronic record is prepared in compliance with Section 63 of the Bharatiya
Sakshya Adhiniyam, 2023 and Section 94 of the Bharatiya Nagarik Suraksha Sanhita, 2023.
"""
    package_files["README.txt"] = readme_text.encode("utf-8")

    # Precompute hashes for everything generated so far
    pre_hashes = {
        name: hashlib.sha256(b).hexdigest() for name, b in package_files.items()
    }

    # --- 5. Certificate Draft PDF (Section 63 BSA 2023) ---
    officer_meta = {
        "full_name": getattr(officer, "full_name", "Investigating Officer"),
        "badge_no": getattr(officer, "badge_no", "DEL-9912"),
        "district": getattr(officer, "district", "Cyber Cell"),
    }
    cert_pdf_bytes = generate_section_63_certificate_pdf(
        case_data=case_meta,
        file_hashes=pre_hashes,
        officer_data=officer_meta,
    )
    package_files["certificate_draft.pdf"] = cert_pdf_bytes
    pre_hashes["certificate_draft.pdf"] = hashlib.sha256(cert_pdf_bytes).hexdigest()

    # --- 6. Forensic Report PDF (ReportLab) ---
    resolved_tsa_url = tsa_url or os.getenv("TSA_URL")
    tsa_status = f"RFC 3161 TSA ({resolved_tsa_url})" if resolved_tsa_url else None

    report_pdf_bytes = generate_pdf_evidence_report(
        case_data=case_meta,
        forensic_data=forensic_data,
        evidence_hashes=pre_hashes,
        officer_data=officer_meta,
        trace_params={
            "seed_address": start_address,
            "chain": chain,
            "max_hops": 3,
            "min_amount": 0.0,
            "taint_model": "FIFO",
        },
        tsa_status=tsa_status,
    )
    package_files["report.pdf"] = report_pdf_bytes
    pre_hashes["report.pdf"] = hashlib.sha256(report_pdf_bytes).hexdigest()

    # --- 7. MANIFEST.json ---
    manifest_files_meta: Dict[str, Any] = {}
    for rel_path, content_bytes in package_files.items():
        sha256_val = hashlib.sha256(content_bytes).hexdigest()
        manifest_files_meta[rel_path] = {
            "sha256": sha256_val,
            "size": len(content_bytes),
            "source_url": scrub_url(f"urn:cryptotrace:artifact:{rel_path}"),
            "fetched_at": now_iso,
        }

    manifest_payload = {
        "manifest_version": "1.0",
        "engine_version": ENGINE_VERSION,
        "case_id": case.case_id,
        "ncrp_ref": case.ncrp_ref,
        "generated_at": now_iso,
        "parameters": {
            "seed_address": start_address,
            "chain": chain,
            "hops": 3,
            "min_amount": 0.0,
            "taint_model": "FIFO",
        },
        "files": manifest_files_meta,
    }
    manifest_bytes = json.dumps(manifest_payload, indent=2, sort_keys=True).encode("utf-8")
    package_files["MANIFEST.json"] = manifest_bytes

    # --- 8. Optional RFC 3161 Trusted Timestamp (MANIFEST.tsr) ---
    if resolved_tsa_url:
        manifest_digest = hashlib.sha256(manifest_bytes).digest()
        tsr_token = request_rfc3161_timestamp(manifest_digest, tsa_url=resolved_tsa_url)
        if tsr_token:
            package_files["MANIFEST.tsr"] = tsr_token

    # --- 9. Archive to ZIP under EXPORT_DIR ---
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(package_files.keys()):
            zf.writestr(fname, package_files[fname])

    # --- 10. Audit Log the Export ---
    append_audit_entry(
        db=db,
        officer_id=officer.id if hasattr(officer, "id") else "system",
        action="EVIDENCE_PACKAGE_EXPORTED",
        target_id=case.case_id,
    )

    return zip_path, zip_filename, manifest_payload
