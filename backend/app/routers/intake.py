"""Complaint Intake & Guarded Extraction API Router.
Accepts raw multilingual cybercrime complaints, redacts PII, extracts verified addresses
and facts, and provisions cases under strict evidentiary containment.
Reference: Phase 9 — Complaint intake with guarded extraction, SIH26183.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Profile,
    Case,
    WalletSubmission,
    AnalysisRun,
    ComplaintIntake,
    generate_uuid,
    utc_now,
)
from app.security import get_current_officer
from app.schemas import (
    IntakeRequest,
    IntakeResponse,
    CreateCaseFromIntakeRequest,
    CreateCaseFromIntakeResponse,
)
from app.services.complaint_extractor import ComplaintIntakeEngine
from app.services.audit import append_audit_entry


router = APIRouter(prefix="/api/intake", tags=["Complaint Intake"])
router_v1 = APIRouter(prefix="/api/v1/intake", tags=["Complaint Intake (v1)"])


def handle_intake_processing(
    req: IntakeRequest,
    current_officer: Profile,
    db: Session,
) -> IntakeResponse:
    """Execute guarded extraction on raw complaint text and audit-log intake."""
    if not req.complaint_text or not req.complaint_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complaint text must not be empty.",
        )

    engine = ComplaintIntakeEngine()
    result = engine.process_complaint(req.complaint_text, req.language)

    # Persist intake record (original text stored ONLY in DB, never in logs)
    intake_id = generate_uuid()
    intake_rec = ComplaintIntake(
        id=intake_id,
        officer_id=current_officer.id,
        original_text=req.complaint_text,
        masked_text=result["masked_text"],
        language=req.language,
        provider_used=result["provider"],
        extraction_mode="deterministic" if result["is_deterministic"] else "ai_guarded",
        extracted_data=result,
        accepted_addresses=result["accepted_addresses"],
        near_misses=result["near_misses"],
        created_case_id=None,
    )
    db.add(intake_rec)
    db.flush()

    # Append to tamper-evident audit log
    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="COMPLAINT_INTAKE_PROCESSED",
        target_id=intake_id,
    )

    db.commit()
    db.refresh(intake_rec)

    return IntakeResponse(
        id=intake_rec.id,
        provider=result["provider"],
        is_deterministic=result["is_deterministic"],
        mode_banner=result["mode_banner"],
        provider_note=result.get("provider_note"),
        masked_text=result["masked_text"],
        pii_redacted_count=result["pii_redacted_count"],
        accepted_addresses=result["accepted_addresses"],
        near_misses=result["near_misses"],
        extracted_facts=result["extracted_facts"],
        rejected_facts=result["rejected_facts"],
        summary=result["summary"],
        translation_en=result.get("translation_en"),
        dpdp_notice=result["dpdp_notice"],
        created_case_id=intake_rec.created_case_id,
        created_at=intake_rec.created_at,
    )


def handle_create_case_from_intake(
    intake_id: str,
    req: CreateCaseFromIntakeRequest,
    current_officer: Profile,
    db: Session,
) -> CreateCaseFromIntakeResponse:
    """Create a new case from verified intake addresses and extracted metadata."""
    intake = db.query(ComplaintIntake).filter(ComplaintIntake.id == intake_id).first()
    if not intake:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint intake record '{intake_id}' not found.",
        )

    # RLS clearance check
    if (
        current_officer.role == "INVESTIGATOR"
        and intake.officer_id
        and intake.officer_id != current_officer.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Intake belongs to another officer.",
        )

    # Resolve addresses to attach
    addrs_to_use = req.accepted_addresses
    if not addrs_to_use:
        # Fall back to all accepted addresses from extraction
        addrs_to_use = [
            a["address"] for a in (intake.accepted_addresses or []) if isinstance(a, dict) and "address" in a
        ]

    if not addrs_to_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one accepted cryptocurrency wallet address is required to create a case.",
        )

    # Extract metadata from intake facts if available
    facts = intake.extracted_data.get("extracted_facts", []) if isinstance(intake.extracted_data, dict) else []
    extracted_loss = None
    for f in facts:
        if isinstance(f, dict) and f.get("fact_type") == "victim_loss_inr" and f.get("value") is not None:
            try:
                extracted_loss = float(f["value"])
                break
            except Exception:
                pass

    case_id = generate_uuid()
    ncrp_ref = (
        req.ncrp_ref
        or f"NCRP/2026/IN-{int(utc_now().timestamp()) % 100000}"
    )

    new_case = Case(
        case_id=case_id,
        ncrp_ref=ncrp_ref,
        amount_inr=extracted_loss,
        assigned_officer_id=current_officer.id,
        status="OPEN",
    )
    db.add(new_case)
    db.flush()

    # Create wallet submissions and pending analysis runs for each address
    for addr in addrs_to_use:
        # Find detected chain if available in accepted_addresses
        detected_chain = "ETH"
        for acc in (intake.accepted_addresses or []):
            if isinstance(acc, dict) and acc.get("address") == addr:
                detected_chain = acc.get("primary_chain", "ETH")
                break

        sub = WalletSubmission(
            submission_id=generate_uuid(),
            case_id=new_case.case_id,
            chain=detected_chain,
            address=addr,
        )
        db.add(sub)
        db.flush()

        run = AnalysisRun(
            run_id=generate_uuid(),
            submission_id=sub.submission_id,
            status="PENDING",
        )
        db.add(run)
        db.flush()

    # Link case to intake
    intake.created_case_id = new_case.case_id

    # Append audit log
    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="CASE_CREATED_FROM_INTAKE",
        target_id=new_case.case_id,
    )

    db.commit()
    db.refresh(new_case)

    return CreateCaseFromIntakeResponse(
        case_id=new_case.case_id,
        ncrp_ref=new_case.ncrp_ref,
        message=f"Case successfully provisioned with {len(addrs_to_use)} lead address(es).",
        accepted_addresses_count=len(addrs_to_use),
    )


# Register endpoints on both /api/intake and /api/v1/intake
@router.post("", response_model=IntakeResponse)
def process_intake(
    req: IntakeRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Process cybercrime complaint with PII masking and deterministic/guarded extraction."""
    return handle_intake_processing(req, current_officer, db)


@router_v1.post("", response_model=IntakeResponse)
def process_intake_v1(
    req: IntakeRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Process cybercrime complaint with PII masking and deterministic/guarded extraction (v1)."""
    return handle_intake_processing(req, current_officer, db)


@router.post("/{intake_id}/create-case", response_model=CreateCaseFromIntakeResponse)
def create_case_from_intake(
    intake_id: str,
    req: CreateCaseFromIntakeRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Create a new case from verified intake addresses."""
    return handle_create_case_from_intake(intake_id, req, current_officer, db)


@router_v1.post("/{intake_id}/create-case", response_model=CreateCaseFromIntakeResponse)
def create_case_from_intake_v1(
    intake_id: str,
    req: CreateCaseFromIntakeRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Create a new case from verified intake addresses (v1)."""
    return handle_create_case_from_intake(intake_id, req, current_officer, db)
