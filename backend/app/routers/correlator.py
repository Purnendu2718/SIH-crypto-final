"""UPI-UTR Correlator API Router.
Enables forensic correlation of victim-reported banking/UPI UTRs against
on-chain transactions and off-ramp deposit flows.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Case, Profile, WalletSubmission, TracePath
from app.schemas import UTRCorrelationRequest, UTRCorrelationResult
from app.security import get_current_officer
from app.services.upi_correlator import UPICorrelator
from app.services.adapters.fixture_adapter import FixtureAdapter
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/api/correlator", tags=["UPI-UTR Correlator"])


@router.post("/match", response_model=UTRCorrelationResult)
def correlate_standalone(
    req: UTRCorrelationRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Correlate a victim UTR and INR amount against on-chain transactions for an address.
    Uses active chain adapter (FixtureAdapter for offline/demo).
    """
    adapter = FixtureAdapter()
    txs = []
    if req.address:
        tx_objs = adapter.get_transactions(req.address, req.chain or "ETH")
        txs = [
            {
                "tx_hash": t.tx_hash,
                "chain": t.chain,
                "from_address": t.from_address,
                "to_address": t.to_address,
                "value": t.value,
                "value_inr": t.value_inr,
                "timestamp": t.timestamp.isoformat() if t.timestamp else None,
            }
            for t in tx_objs
        ]

    result = UPICorrelator.correlate(
        victim_utr=req.victim_utr,
        reported_amount_inr=req.amount_inr,
        utr_timestamp=req.utr_timestamp,
        transactions=txs,
        time_tolerance_minutes=req.time_tolerance_minutes,
        amount_tolerance_percent=req.amount_tolerance_percent,
        exchange_rate_inr=req.exchange_rate_inr,
    )

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="UPI_UTR_CORRELATION_STANDALONE",
        target_id=req.victim_utr,
    )

    return result


@router.post("/case/{case_id}", response_model=UTRCorrelationResult)
def correlate_case_utr(
    case_id: str,
    time_tolerance_minutes: float = Query(120.0, description="Time window in minutes"),
    amount_tolerance_percent: float = Query(5.0, description="Amount tolerance percentage"),
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Run UPI-UTR correlation for a specific case's victim records.
    Evaluates against all transactions discovered across the case's wallet submissions.
    """
    case = (
        db.query(Case)
        .options(
            joinedload(Case.wallet_submissions)
            .joinedload(WalletSubmission.analysis_runs)
        )
        .filter(Case.case_id == case_id)
        .first()
    )

    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found."
        )

    # RLS Check
    if current_officer.role == "INVESTIGATOR" and case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance."
        )

    if not case.victim_utr:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This case has no victim UTR recorded."
        )

    amount_inr = float(case.amount_inr or 0.0)
    utr_timestamp = case.victim_utr_timestamp or case.created_at or datetime.now(timezone.utc)

    # Collect transactions from fixture adapter or trace paths
    adapter = FixtureAdapter()
    all_txs = []
    seen_hashes = set()

    for sub in case.wallet_submissions:
        tx_objs = adapter.get_transactions(sub.address, sub.chain)
        for t in tx_objs:
            if t.tx_hash not in seen_hashes:
                seen_hashes.add(t.tx_hash)
                all_txs.append(
                    {
                        "tx_hash": t.tx_hash,
                        "chain": t.chain,
                        "from_address": t.from_address,
                        "to_address": t.to_address,
                        "value": t.value,
                        "value_inr": t.value_inr,
                        "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                    }
                )

    result = UPICorrelator.correlate(
        victim_utr=case.victim_utr,
        reported_amount_inr=amount_inr,
        utr_timestamp=utr_timestamp,
        transactions=all_txs,
        time_tolerance_minutes=time_tolerance_minutes,
        amount_tolerance_percent=amount_tolerance_percent,
    )

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="UPI_UTR_CASE_CORRELATION",
        target_id=case_id,
    )

    return result
