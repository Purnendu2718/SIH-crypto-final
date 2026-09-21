"""Golden Hour Watchlist API Router.
Provides CRUD endpoints for real-time suspect address monitoring and on-demand polling.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WatchlistEntry, Case, Profile, generate_uuid, utc_now
from app.schemas import (
    WatchlistEntryCreate,
    WatchlistEntryOut,
    WatchlistPollResult,
)
from app.security import get_current_officer
from app.services.watchlist_service import poll_all_watchlist_entries, check_watchlist_entry
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/api/watchlist", tags=["Golden Hour Watchlist"])


@router.get("", response_model=List[WatchlistEntryOut])
def list_watchlist_entries(
    case_id: Optional[str] = Query(None, description="Filter by case ID"),
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Retrieve active Golden Hour monitoring watchlist entries."""
    query = db.query(WatchlistEntry)
    if current_officer.role == "INVESTIGATOR":
        query = query.join(Case).filter(Case.assigned_officer_id == current_officer.id)
    if case_id:
        query = query.filter(WatchlistEntry.case_id == case_id)
    return query.order_by(WatchlistEntry.created_at.desc()).all()


@router.post("", response_model=WatchlistEntryOut, status_code=status.HTTP_201_CREATED)
def create_watchlist_entry(
    data: WatchlistEntryCreate,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Add a suspect address to the Golden Hour monitoring watchlist."""
    case = db.query(Case).filter(Case.case_id == data.case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{data.case_id}' not found."
        )

    # RLS Check: Investigator can only add to own cases
    if current_officer.role == "INVESTIGATOR" and case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case is assigned to another officer.",
        )

    # Check if already monitored for this case
    existing = (
        db.query(WatchlistEntry)
        .filter(
            WatchlistEntry.case_id == data.case_id,
            WatchlistEntry.address.ilike(data.address.strip()),
        )
        .first()
    )
    if existing:
        return existing

    new_entry = WatchlistEntry(
        id=generate_uuid(),
        address=data.address.strip(),
        chain=data.chain.upper(),
        case_id=data.case_id,
        alert_channel=data.alert_channel or "TELEGRAM",
        status="ACTIVE",
        created_at=utc_now(),
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="WATCHLIST_ENTRY_CREATED",
        target_id=new_entry.id,
    )

    return new_entry


@router.get("/{entry_id}", response_model=WatchlistEntryOut)
def get_watchlist_entry(
    entry_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Get single watchlist entry details."""
    entry = db.query(WatchlistEntry).filter(WatchlistEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist entry '{entry_id}' not found."
        )

    # RLS Check
    if current_officer.role == "INVESTIGATOR" and entry.case and entry.case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance.",
        )
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_200_OK)
def delete_watchlist_entry(
    entry_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Remove an address from the Golden Hour watchlist."""
    entry = db.query(WatchlistEntry).filter(WatchlistEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Watchlist entry '{entry_id}' not found."
        )

    # RLS Check
    if current_officer.role == "INVESTIGATOR" and entry.case and entry.case.assigned_officer_id != current_officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance.",
        )

    db.delete(entry)
    db.commit()

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="WATCHLIST_ENTRY_DELETED",
        target_id=entry_id,
    )

    return {"message": f"Watchlist entry '{entry_id}' deleted successfully."}


@router.post("/poll-now", response_model=WatchlistPollResult)
def poll_watchlist_now(
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Trigger an immediate scan of all watchlisted addresses for outbound off-ramp movements."""
    result = poll_all_watchlist_entries(db=db)
    return WatchlistPollResult(
        total_checked=result["total_checked"],
        alerts_fired=result["alerts_fired"],
        alert_details=result["alert_details"],
    )
