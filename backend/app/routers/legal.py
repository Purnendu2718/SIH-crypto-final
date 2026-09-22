"""Legal Mapping Engine API Router.
Provides deterministic penal statutory suggestions for investigating officers.
Reference: Phase 8 — Legal mapping engine, Ministry of Home Affairs / I4C.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Case, Profile, WalletSubmission, AnalysisRun
from app.security import get_current_officer
from app.schemas import LegalSuggestionsRequest, LegalSuggestionsResponse
from app.legal.engine import LegalRulesEngine

router = APIRouter(prefix="/api/cases", tags=["Legal Suggestions"])
router_v1 = APIRouter(prefix="/api/v1/cases", tags=["Legal Suggestions (v1)"])

# Shared engine instance
_engine: Optional[LegalRulesEngine] = None


def get_legal_engine() -> LegalRulesEngine:
    global _engine
    if _engine is None:
        _engine = LegalRulesEngine()
    return _engine


def handle_legal_suggestions(
    case_id: str,
    req: LegalSuggestionsRequest,
    current_officer: Profile,
    db: Session,
) -> Dict[str, Any]:
    """Execute deterministic legal mapping rules for a case."""
    query = (
        db.query(Case)
        .options(
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.trace_paths),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.typologies),
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
            .joinedload(AnalysisRun.attributions),
        )
        .filter(Case.case_id == case_id)
    )

    case = query.first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with ID '{case_id}' not found.",
        )

    # Database-level RLS check
    if (
        current_officer.role == "INVESTIGATOR"
        and case.assigned_officer_id
        and case.assigned_officer_id != current_officer.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case is assigned to another officer.",
        )

    # Resolve offence date: request input > case victim_utr_timestamp > None
    offence_date = req.offence_date
    if not offence_date:
        if case.victim_utr_timestamp:
            offence_date = case.victim_utr_timestamp.strftime("%Y-%m-%d")

    # Resolve trace result: request input > case stored analysis run
    trace_result: Dict[str, Any] = req.trace_result or {}
    if not trace_result and case.wallet_submissions:
        # Find latest completed or available analysis run
        latest_run = None
        for sub in case.wallet_submissions:
            for run in sub.analysis_runs:
                if latest_run is None or (run.started_at and latest_run.started_at and run.started_at > latest_run.started_at):
                    latest_run = run

        if latest_run:
            paths = [
                {
                    "from": tp.from_addr,
                    "to": tp.to_addr,
                    "hop_index": tp.hop_index,
                    "chain": tp.chain,
                    "value": float(tp.value) if tp.value is not None else None,
                }
                for tp in (latest_run.trace_paths or [])
            ]
            typos = [
                {"typology": t.typology}
                for t in (latest_run.typologies or [])
            ]
            vasp_entity = (
                latest_run.attributions[0].matched_entity
                if latest_run.attributions
                else None
            )
            trace_result = {
                "paths": paths,
                "typologies": typos,
                "vasp_name": vasp_entity,
                "reached_vasp": bool(vasp_entity),
                "total_hops": len(paths),
            }

    case_data = {
        "ncrp_ref": case.ncrp_ref,
        "victim_utr": case.victim_utr,
        "amount_inr": float(case.amount_inr) if case.amount_inr is not None else None,
    }

    engine = get_legal_engine()
    try:
        result = engine.suggest_provisions(
            typology=req.typology,
            offence_date=offence_date,
            trace_result=trace_result,
            case_data=case_data,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )

    return result


@router.post("/{case_id}/legal-suggestions", response_model=LegalSuggestionsResponse)
def get_case_legal_suggestions(
    case_id: str,
    req: LegalSuggestionsRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Deterministic statutory suggestions mapping cybercrime typology to penal provisions."""
    return handle_legal_suggestions(case_id, req, current_officer, db)


@router_v1.post("/{case_id}/legal-suggestions", response_model=LegalSuggestionsResponse)
def get_case_legal_suggestions_v1(
    case_id: str,
    req: LegalSuggestionsRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Deterministic statutory suggestions mapping cybercrime typology to penal provisions (v1)."""
    return handle_legal_suggestions(case_id, req, current_officer, db)
