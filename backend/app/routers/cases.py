"""Case management and preloaded caseload query routes with database-level RLS.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Case,
    Profile,
    WalletSubmission,
    AnalysisRun,
    Attribution,
    generate_uuid,
    utc_now,
)
from app.schemas import (
    CaseCreate,
    CaseOut,
    WalletSubmissionSummary,
    AnalysisRunSummary,
    AttributionSummary,
)
from app.security import get_current_officer

router = APIRouter(prefix="/api/cases", tags=["Cases & Caseload"])


@router.get("", response_model=List[CaseOut])
def get_cases(
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Work-history preload endpoint.
    Queries cases joined to submissions, analysis runs, and attributions.
    Enforces RLS at the database level:
      - INVESTIGATOR: strictly filtered by assigned_officer_id == current_officer.id
      - SUPERVISOR / ADMIN: access to all cases across the department / district.
    Ordered by created_at desc.
    """
    query = (
        db.query(Case)
        .options(
            joinedload(Case.assigned_officer),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.attributions),
        )
    )

    # Database-level Row-Level Security (RLS) enforcement
    if current_officer.role == "INVESTIGATOR":
        query = query.filter(Case.assigned_officer_id == current_officer.id)
    # SUPERVISOR and ADMIN see all department cases

    cases = query.order_by(Case.created_at.desc()).all()

    results: List[CaseOut] = []
    for c in cases:
        submissions_out: List[WalletSubmissionSummary] = []
        latest_entity = None
        latest_confidence = None

        for sub in c.wallet_submissions:
            runs_out: List[AnalysisRunSummary] = []
            for run in sub.analysis_runs:
                attrs_out = [
                    AttributionSummary(
                        id=attr.id,
                        matched_entity=attr.matched_entity,
                        rule_fired=attr.rule_fired,
                        confidence=float(attr.confidence),
                        score_breakdown=attr.score_breakdown,
                    )
                    for attr in run.attributions
                ]
                if attrs_out and latest_entity is None:
                    latest_entity = attrs_out[0].matched_entity
                    latest_confidence = attrs_out[0].confidence

                runs_out.append(
                    AnalysisRunSummary(
                        run_id=run.run_id,
                        status=run.status,
                        started_at=run.started_at,
                        completed_at=run.completed_at,
                        attributions=attrs_out,
                    )
                )

            submissions_out.append(
                WalletSubmissionSummary(
                    submission_id=sub.submission_id,
                    chain=sub.chain,
                    address=sub.address,
                    submitted_at=sub.submitted_at,
                    analysis_runs=runs_out,
                )
            )

        results.append(
            CaseOut(
                case_id=c.case_id,
                ncrp_ref=c.ncrp_ref,
                victim_utr=c.victim_utr,
                victim_utr_timestamp=c.victim_utr_timestamp,
                amount_inr=float(c.amount_inr) if c.amount_inr is not None else None,
                assigned_officer_id=c.assigned_officer_id,
                assigned_officer_name=c.assigned_officer.full_name if c.assigned_officer else "Unassigned",
                status=c.status or "OPEN",
                created_at=c.created_at,
                submissions=submissions_out,
                latest_entity=latest_entity,
                latest_confidence=latest_confidence,
            )
        )

    return results


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    data: CaseCreate,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Create a new case assigned to the logged-in officer."""
    new_case = Case(
        case_id=generate_uuid(),
        ncrp_ref=data.ncrp_ref or f"NCRP/2026/{int(datetime.now(timezone.utc).timestamp()) % 100000}",
        victim_utr=data.victim_utr,
        victim_utr_timestamp=data.victim_utr_timestamp,
        amount_inr=data.amount_inr,
        assigned_officer_id=current_officer.id,
        status="OPEN",
    )
    db.add(new_case)
    db.flush()

    submissions_out = []
    if data.suspect_address:
        submission = WalletSubmission(
            submission_id=generate_uuid(),
            case_id=new_case.case_id,
            chain=data.chain or "ETH",
            address=data.suspect_address,
        )
        db.add(submission)
        db.flush()

        # Create an initial pending analysis run
        run = AnalysisRun(
            run_id=generate_uuid(),
            submission_id=submission.submission_id,
            status="PENDING",
        )
        db.add(run)
        db.flush()

        submissions_out.append(
            WalletSubmissionSummary(
                submission_id=submission.submission_id,
                chain=submission.chain,
                address=submission.address,
                submitted_at=submission.submitted_at,
                analysis_runs=[
                    AnalysisRunSummary(
                        run_id=run.run_id,
                        status=run.status,
                        started_at=run.started_at,
                        completed_at=None,
                        attributions=[],
                    )
                ],
            )
        )

    db.commit()
    db.refresh(new_case)

    return CaseOut(
        case_id=new_case.case_id,
        ncrp_ref=new_case.ncrp_ref,
        victim_utr=new_case.victim_utr,
        victim_utr_timestamp=new_case.victim_utr_timestamp,
        amount_inr=float(new_case.amount_inr) if new_case.amount_inr is not None else None,
        assigned_officer_id=current_officer.id,
        assigned_officer_name=current_officer.full_name,
        status=new_case.status,
        created_at=new_case.created_at,
        submissions=submissions_out,
        latest_entity=None,
        latest_confidence=None,
    )


@router.get("/{case_id}", response_model=CaseOut)
def get_case_by_id(
    case_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Retrieve an individual case by case_id with database RLS enforcement."""
    query = (
        db.query(Case)
        .options(
            joinedload(Case.assigned_officer),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.attributions),
        )
        .filter(Case.case_id == case_id)
    )

    if current_officer.role == "INVESTIGATOR":
        query = query.filter(Case.assigned_officer_id == current_officer.id)

    case_obj = query.first()
    if not case_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found or access unauthorized under current officer clearance."
        )

    submissions_out: List[WalletSubmissionSummary] = []
    latest_entity = None
    latest_confidence = None

    for sub in case_obj.wallet_submissions:
        runs_out: List[AnalysisRunSummary] = []
        for run in sub.analysis_runs:
            attrs_out = [
                AttributionSummary(
                    id=attr.id,
                    matched_entity=attr.matched_entity,
                    rule_fired=attr.rule_fired,
                    confidence=float(attr.confidence),
                    score_breakdown=attr.score_breakdown,
                )
                for attr in run.attributions
            ]
            if attrs_out and latest_entity is None:
                latest_entity = attrs_out[0].matched_entity
                latest_confidence = attrs_out[0].confidence

            runs_out.append(
                AnalysisRunSummary(
                    run_id=run.run_id,
                    status=run.status,
                    started_at=run.started_at,
                    completed_at=run.completed_at,
                    attributions=attrs_out,
                )
            )

        submissions_out.append(
            WalletSubmissionSummary(
                submission_id=sub.submission_id,
                chain=sub.chain,
                address=sub.address,
                submitted_at=sub.submitted_at,
                analysis_runs=runs_out,
            )
        )

    return CaseOut(
        case_id=case_obj.case_id,
        ncrp_ref=case_obj.ncrp_ref,
        victim_utr=case_obj.victim_utr,
        victim_utr_timestamp=case_obj.victim_utr_timestamp,
        amount_inr=float(case_obj.amount_inr) if case_obj.amount_inr is not None else None,
        assigned_officer_id=case_obj.assigned_officer_id,
        assigned_officer_name=case_obj.assigned_officer.full_name if case_obj.assigned_officer else "Unassigned",
        status=case_obj.status or "OPEN",
        created_at=case_obj.created_at,
        submissions=submissions_out,
        latest_entity=latest_entity,
        latest_confidence=latest_confidence,
    )


@router.post("/seed-demo")
def seed_demo_cases(db: Session = Depends(get_db)):
    """Seed demo accounts and sample cases for Phase 1 verification."""
    from app.security import hash_password

    # 1. Create Investigator 1 (Officer Sharma)
    sharma = db.query(Profile).filter(Profile.email == "sharma@sentinel.gov.in").first()
    if not sharma:
        sharma = Profile(
            id=generate_uuid(),
            email="sharma@sentinel.gov.in",
            password_hash=hash_password("SentinelPass123!"),
            full_name="SI Vikram Sharma",
            badge_no="DEL-8842",
            role="INVESTIGATOR",
            district="Cyber Cell New Delhi",
        )
        db.add(sharma)
        db.flush()

    # 2. Create Investigator 2 (Officer Patel)
    patel = db.query(Profile).filter(Profile.email == "patel@sentinel.gov.in").first()
    if not patel:
        patel = Profile(
            id=generate_uuid(),
            email="patel@sentinel.gov.in",
            password_hash=hash_password("SentinelPass123!"),
            full_name="Inspector Ananya Patel",
            badge_no="MUM-3190",
            role="INVESTIGATOR",
            district="Cyber Crime Unit Mumbai",
        )
        db.add(patel)
        db.flush()

    # 3. Create Supervisor (ACP Verma)
    verma = db.query(Profile).filter(Profile.email == "verma@sentinel.gov.in").first()
    if not verma:
        verma = Profile(
            id=generate_uuid(),
            email="verma@sentinel.gov.in",
            password_hash=hash_password("SentinelPass123!"),
            full_name="ACP Rajesh Verma",
            badge_no="HQ-0012",
            role="SUPERVISOR",
            district="I4C Coordination HQ",
        )
        db.add(verma)
        db.flush()

    # 4. Create Cases for Sharma
    case1_exists = db.query(Case).filter(Case.ncrp_ref == "NCRP/2026/DL-49102").first()
    if not case1_exists:
        c1 = Case(
            case_id=generate_uuid(),
            ncrp_ref="NCRP/2026/DL-49102",
            victim_utr="UPI-429188092144",
            amount_inr=350000.0,
            assigned_officer_id=sharma.id,
            status="ANALYZED",
        )
        db.add(c1)
        db.flush()

        s1 = WalletSubmission(
            submission_id=generate_uuid(),
            case_id=c1.case_id,
            chain="ETH",
            address="0x71C...4f9b",
        )
        db.add(s1)
        db.flush()

        r1 = AnalysisRun(
            run_id=generate_uuid(),
            submission_id=s1.submission_id,
            status="COMPLETED",
            completed_at=utc_now(),
        )
        db.add(r1)
        db.flush()

        a1 = Attribution(
            id=generate_uuid(),
            run_id=r1.run_id,
            matched_entity="CoinDCX",
            rule_fired="SWEEP_TO_HOT_WALLET",
            confidence=0.88,
            score_breakdown={"sweep_match": 0.35, "path_proximity": 0.20, "deposit_similarity": 0.15, "temporal": 0.18},
        )
        db.add(a1)

    # 5. Create Cases for Patel
    case2_exists = db.query(Case).filter(Case.ncrp_ref == "NCRP/2026/MH-82190").first()
    if not case2_exists:
        c2 = Case(
            case_id=generate_uuid(),
            ncrp_ref="NCRP/2026/MH-82190",
            victim_utr="UPI-771928301928",
            amount_inr=820000.0,
            assigned_officer_id=patel.id,
            status="ANALYZED",
        )
        db.add(c2)
        db.flush()

        s2 = WalletSubmission(
            submission_id=generate_uuid(),
            case_id=c2.case_id,
            chain="TRON",
            address="TR7NHq...mY",
        )
        db.add(s2)
        db.flush()

        r2 = AnalysisRun(
            run_id=generate_uuid(),
            submission_id=s2.submission_id,
            status="COMPLETED",
            completed_at=utc_now(),
        )
        db.add(r2)
        db.flush()

        a2 = Attribution(
            id=generate_uuid(),
            run_id=r2.run_id,
            matched_entity="WazirX",
            rule_fired="DEPOSIT_CLUSTER_MATCH",
            confidence=0.74,
            score_breakdown={"cluster_match": 0.30, "temporal": 0.20, "path_proximity": 0.24},
        )
        db.add(a2)

    db.commit()
    return {"message": "Demo officers and cases successfully seeded.", "accounts": ["sharma@sentinel.gov.in", "patel@sentinel.gov.in", "verma@sentinel.gov.in"]}
