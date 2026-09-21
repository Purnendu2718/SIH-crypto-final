"""Analysis execution, trace, attribution, typology, taint, and risk assessment router.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, WalletSubmission, AnalysisRun
from app.security import get_current_officer
from app.services import run_full_forensic_pipeline

router = APIRouter(prefix="/api/analysis", tags=["Trace & Analysis"])


class QuickTraceRequest(BaseModel):
    address: str
    chain: str = "ETH"
    max_hops: int = 15
    dust_threshold: float = 0.001
    stolen_principal: Optional[float] = None


@router.post("/quick-trace")
def execute_quick_trace(
    req: QuickTraceRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Execute real-time end-to-end forensics:
    Trace -> Attribution -> Typology Detection -> FIFO Taint -> Composite Risk.
    """
    return run_full_forensic_pipeline(
        start_address=req.address,
        chain=req.chain,
        stolen_principal=req.stolen_principal,
        max_hops=req.max_hops,
        dust_threshold=req.dust_threshold,
        db=db,
    )


@router.post("/run/{submission_id}")
def run_submission_trace(
    submission_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Execute end-to-end forensic analysis for a submitted suspect wallet."""
    submission = db.query(WalletSubmission).filter(WalletSubmission.submission_id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"WalletSubmission '{submission_id}' not found.")

    if submission.case and current_officer.role == "INVESTIGATOR" and submission.case.assigned_officer_id and submission.case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case is assigned to another officer.",
        )

    # Find or create run
    run = db.query(AnalysisRun).filter(AnalysisRun.submission_id == submission_id).order_by(AnalysisRun.started_at.desc()).first()
    if not run:
        from app.models import generate_uuid
        run = AnalysisRun(
            run_id=generate_uuid(),
            submission_id=submission.submission_id,
            status="PENDING",
        )
        db.add(run)
        db.flush()

    run_id = run.run_id

    # Get case amount if available for taint calculation
    stolen_principal = float(submission.case.amount_inr) if (submission.case and submission.case.amount_inr) else None

    result = run_full_forensic_pipeline(
        start_address=submission.address,
        chain=submission.chain,
        run_id=run_id,
        stolen_principal=stolen_principal,
        db=db,
    )

    if submission.case:
        submission.case.status = "ANALYZED"
        db.commit()

    return result


@router.get("/run/{run_id}")
def get_run_analysis(
    run_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Retrieve full analysis report for a run."""
    run = db.query(AnalysisRun).filter(AnalysisRun.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"AnalysisRun '{run_id}' not found.")

    sub = run.submission
    if sub and sub.case and current_officer.role == "INVESTIGATOR" and sub.case.assigned_officer_id and sub.case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case is assigned to another officer.",
        )

    return run_full_forensic_pipeline(
        start_address=sub.address,
        chain=sub.chain,
        run_id=run.run_id,
        db=db,
    )
