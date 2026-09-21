"""Evidence packages, Section 94 BNSS legal notices, PDF reports, and audit log API.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, Case, WalletSubmission, AnalysisRun, VASPDirectory, AuditLog, EvidencePackage
from app.security import get_current_officer
from app.services import run_full_forensic_pipeline
from app.services.evidence import EvidenceManager
from app.services.audit import append_audit_entry, verify_audit_chain
from app.services.legal_notice import generate_section_94_bnss_notice
from app.services.report_generator import generate_pdf_evidence_report

router = APIRouter(prefix="/api/evidence", tags=["Evidence & Legal Notices"])
audit_router = APIRouter(prefix="/api/audit", tags=["Audit Log"])


# ==============================================================================
# Evidence Package & Legal Notice Endpoints
# ==============================================================================

@router.post("/generate/{run_id}")
def generate_case_evidence(
    run_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Generate complete cryptographic evidence package for an analysis run."""
    run = db.query(AnalysisRun).filter(AnalysisRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found.")

    sub = run.submission
    case = sub.case if sub else None

    # RLS Check: Investigator must be assigned to case if case is assigned
    if current_officer.role == "INVESTIGATOR" and case and case.assigned_officer_id and case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case is assigned to another officer.",
        )

    # Run full forensic pipeline
    stolen_val = float(case.amount_inr) if (case and case.amount_inr) else None
    forensic_data = run_full_forensic_pipeline(
        start_address=sub.address,
        chain=sub.chain,
        run_id=run.run_id,
        stolen_principal=stolen_val,
        db=db,
    )

    # Generate Section 94 BNSS notice
    matched_entity = forensic_data["attribution"].get("matched_entity", "Unknown VASP")
    vasp = db.query(VASPDirectory).filter(VASPDirectory.entity_name == matched_entity).first()
    nodal_contact = vasp.nodal_contact if vasp else f"compliance@{matched_entity.lower().replace(' ', '')}.com"

    tx_hashes = [p["tx_hash"] for p in forensic_data["trace"]["paths"] if p.get("tx_hash")]

    notice_text = generate_section_94_bnss_notice(
        ncrp_ref=case.ncrp_ref if case else "NCRP/2026/UNASSIGNED",
        vasp_name=matched_entity,
        nodal_contact=nodal_contact,
        suspect_address=sub.address,
        chain=sub.chain,
        tx_hashes=tx_hashes,
        amount_inr=float(case.amount_inr) if (case and case.amount_inr) else None,
        victim_utr=case.victim_utr if case else None,
        officer_name=current_officer.full_name,
        badge_no=current_officer.badge_no or "N/A",
        district=current_officer.district or "Cyber Cell",
    )

    # Prepare evidence package with additional files
    additional_files = {
        "section_94_bnss_notice.txt": notice_text.encode("utf-8"),
    }

    # Generate PDF report
    evidence_hashes_pre = {
        "sha256_hash": "pre_computation",
        "merkle_root": "pre_computation",
    }
    case_dict = {
        "ncrp_ref": case.ncrp_ref if case else "NCRP/2026/UNASSIGNED",
        "victim_utr": case.victim_utr if case else "N/A",
        "amount_inr": float(case.amount_inr) if (case and case.amount_inr) else None,
    }
    officer_dict = {
        "full_name": current_officer.full_name,
        "badge_no": current_officer.badge_no,
        "district": current_officer.district,
    }
    pdf_bytes = generate_pdf_evidence_report(
        case_data=case_dict,
        forensic_data=forensic_data,
        evidence_hashes=evidence_hashes_pre,
        officer_data=officer_dict,
    )
    additional_files["forensic_report.pdf"] = pdf_bytes

    # Create Merkle tree package
    package = EvidenceManager.create_evidence_package(
        run_id=run.run_id,
        trace_payload=forensic_data,
        additional_files=additional_files,
        db=db,
    )

    # Append hash-chained audit log
    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="GENERATE_EVIDENCE_PACKAGE",
        target_id=package["package_id"],
    )

    return {
        "package": package,
        "legal_notice": notice_text,
        "forensic_summary": forensic_data,
    }


@router.get("/pdf/{run_id}")
def download_pdf_evidence_report(
    run_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Download court-ready PDF evidence report with Section 63 BSA certificate."""
    run = db.query(AnalysisRun).filter(AnalysisRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found.")

    sub = run.submission
    case = sub.case if sub else None

    # RLS Check: Investigator must be assigned to case if case is assigned
    if current_officer.role == "INVESTIGATOR" and case and case.assigned_officer_id and case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case is assigned to another officer.",
        )

    forensic_data = run_full_forensic_pipeline(
        start_address=sub.address,
        chain=sub.chain,
        run_id=run.run_id,
        db=db,
    )

    evidence_pkg = db.query(EvidencePackage).filter(EvidencePackage.run_id == run_id).first()
    hashes = {
        "sha256_hash": evidence_pkg.sha256_hash if evidence_pkg else "0" * 64,
        "merkle_root": evidence_pkg.merkle_root if evidence_pkg else "0" * 64,
    }

    case_dict = {
        "ncrp_ref": case.ncrp_ref if case else "NCRP/2026/UNASSIGNED",
        "victim_utr": case.victim_utr if case else "N/A",
        "amount_inr": float(case.amount_inr) if (case and case.amount_inr) else None,
    }
    officer_dict = {
        "full_name": current_officer.full_name,
        "badge_no": current_officer.badge_no,
        "district": current_officer.district,
    }

    pdf_bytes = generate_pdf_evidence_report(
        case_data=case_dict,
        forensic_data=forensic_data,
        evidence_hashes=hashes,
        officer_data=officer_dict,
    )

    # Append audit log
    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="DOWNLOAD_PDF_EVIDENCE_REPORT",
        target_id=run_id,
    )

    filename = f"Evidence_Report_{case.ncrp_ref.replace('/', '_') if case else run_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ==============================================================================
# Audit Log Verification Endpoints
# ==============================================================================

@audit_router.get("/verify")
def check_audit_chain_integrity(
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Verify cryptographic integrity of the entire audit chain.
    Detects any database tampering or altered entries.
    """
    return verify_audit_chain(db)


@audit_router.get("/logs")
def get_audit_logs(
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Query audit logs (officer views own, supervisor views all)."""
    query = db.query(AuditLog)
    if current_officer.role == "INVESTIGATOR":
        query = query.filter(AuditLog.officer_id == current_officer.id)

    entries = query.order_by(AuditLog.timestamp.desc()).all()
    return [
        {
            "entry_id": e.entry_id,
            "prev_hash": e.prev_hash,
            "entry_hash": e.entry_hash,
            "officer_id": e.officer_id,
            "action": e.action,
            "target_id": e.target_id,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in entries
    ]
