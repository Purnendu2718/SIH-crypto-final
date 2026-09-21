"""Arjuna AI Case Co-pilot API Router.
Generates plain-English and Hindi prosecution summaries from structured case records.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Case,
    Profile,
    WalletSubmission,
    AnalysisRun,
    Attribution,
    TypologyDetected,
    EvidencePackage,
    TracePath,
    VASPDirectory,
)
from app.schemas import ArjunaSummaryRequest, ArjunaSummaryResponse
from app.security import get_current_officer
from app.services.arjuna_copilot import ArjunaCopilot
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/api/analysis", tags=["Arjuna AI Co-pilot"])


@router.post("/{case_id}/arjuna-summary", response_model=ArjunaSummaryResponse)
@router.get("/{case_id}/arjuna-summary", response_model=ArjunaSummaryResponse)
def get_arjuna_summary(
    case_id: str,
    language: Optional[str] = Query("both", description="Language: 'en', 'hi', or 'both'"),
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Generate or retrieve the Arjuna AI Co-pilot case summary in English and Hindi."""
    case = (
        db.query(Case)
        .options(
            joinedload(Case.assigned_officer),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.attributions),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.typologies),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.evidence_packages),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.trace_paths),
        )
        .filter(Case.case_id == case_id)
        .first()
    )

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found."
        )

    # RLS Enforcement
    if current_officer.role == "INVESTIGATOR" and case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance."
        )

    # Collate case parameters
    suspect_address = "N/A"
    chain = "ETH"
    hop_count = 0
    matched_entity = "Insufficient Evidence"
    confidence = 0.0
    confidence_band = "INSUFFICIENT_EVIDENCE"
    rule_fired = "NO_OFFRAMP_IDENTIFIED"
    typologies = []
    evidence_sha256 = "N/A"

    for sub in case.wallet_submissions:
        suspect_address = sub.address
        chain = sub.chain
        for run in sub.analysis_runs:
            if run.trace_paths:
                hop_count = max(hop_count, len(run.trace_paths))
            if run.attributions:
                attr = run.attributions[0]
                matched_entity = attr.matched_entity
                confidence = float(attr.confidence)
                rule_fired = attr.rule_fired
                if confidence >= 0.85:
                    confidence_band = "VERY_HIGH"
                elif confidence >= 0.65:
                    confidence_band = "HIGH"
                elif confidence >= 0.40:
                    confidence_band = "MEDIUM"
                else:
                    confidence_band = "INSUFFICIENT_EVIDENCE"
            if run.typologies:
                typologies = [t.typology for t in run.typologies]
            if run.evidence_packages:
                evidence_sha256 = run.evidence_packages[0].sha256_hash

    # Lookup nodal contact
    nodal_contact = "compliance@exchange.in"
    if matched_entity and matched_entity != "Insufficient Evidence":
        vasp = db.query(VASPDirectory).filter(VASPDirectory.entity_name == matched_entity).first()
        if vasp and vasp.nodal_contact:
            nodal_contact = vasp.nodal_contact

    case_payload = {
        "case_id": case.case_id,
        "ncrp_ref": case.ncrp_ref or "NCRP/2026/PENDING",
        "victim_utr": case.victim_utr or "N/A",
        "amount_inr": float(case.amount_inr or 0.0),
        "suspect_address": suspect_address,
        "chain": chain,
        "hop_count": hop_count,
        "matched_entity": matched_entity,
        "confidence": confidence,
        "confidence_band": confidence_band,
        "rule_fired": rule_fired,
        "typologies": typologies,
        "taint_percentage": 100.0,
        "risk_score": 85 if confidence >= 0.65 else 45,
        "risk_level": "CRITICAL" if confidence >= 0.65 else "MODERATE",
        "evidence_sha256": evidence_sha256,
        "nodal_contact": nodal_contact,
        "officer_name": current_officer.full_name,
        "district": current_officer.district or "Cyber Crime Unit",
    }

    result = ArjunaCopilot.generate_summary(case_data=case_payload, language=language or "both")

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="ARJUNA_SUMMARY_GENERATED",
        target_id=case_id,
    )

    return ArjunaSummaryResponse(
        case_id=result["case_id"],
        ncrp_ref=result["ncrp_ref"],
        summary_en=result["summary_en"],
        summary_hi=result["summary_hi"],
        factual_verification=result["factual_verification"],
        strict_containment_passed=result["strict_containment_passed"],
    )
