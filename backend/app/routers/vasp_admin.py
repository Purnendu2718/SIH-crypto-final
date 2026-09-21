"""VASP Directory Admin API Router.
Enables administrators (ADMIN role) to curate, add, update, and manage
FIU-IND registered Virtual Asset Service Provider records, nodal contacts, and hot wallets.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import VASPDirectory, Profile
from app.schemas import VASPCreate, VASPUpdate, VASPOut
from app.security import get_current_officer, check_role
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/api/admin/vasps", tags=["VASP Directory Admin"])


@router.get("", response_model=List[VASPOut])
def list_vasps(
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """List all registered exchanges and VASPs."""
    return db.query(VASPDirectory).order_by(VASPDirectory.entity_name.asc()).all()


@router.get("/{entity_name}", response_model=VASPOut)
def get_vasp_detail(
    entity_name: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Retrieve details for a single VASP by name."""
    vasp = db.query(VASPDirectory).filter(VASPDirectory.entity_name == entity_name).first()
    if not vasp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VASP entity '{entity_name}' not found."
        )
    return vasp


@router.post("", response_model=VASPOut, status_code=status.HTTP_201_CREATED)
def create_vasp(
    data: VASPCreate,
    current_officer: Profile = Depends(check_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Create a new VASP directory entry (strictly ADMIN role only)."""
    existing = db.query(VASPDirectory).filter(VASPDirectory.entity_name == data.entity_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VASP entity '{data.entity_name}' already exists."
        )

    new_vasp = VASPDirectory(
        entity_name=data.entity_name,
        chain=data.chain or "ETH",
        hot_wallet_addresses=data.hot_wallet_addresses or [],
        fiu_ind_registered=data.fiu_ind_registered,
        sla_hours=data.sla_hours,
        nodal_contact=data.nodal_contact,
    )
    db.add(new_vasp)
    db.commit()
    db.refresh(new_vasp)

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="VASP_DIRECTORY_CREATED",
        target_id=data.entity_name,
    )

    return new_vasp


@router.put("/{entity_name}", response_model=VASPOut)
def update_vasp(
    entity_name: str,
    data: VASPUpdate,
    current_officer: Profile = Depends(check_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Update VASP details (strictly ADMIN role only)."""
    vasp = db.query(VASPDirectory).filter(VASPDirectory.entity_name == entity_name).first()
    if not vasp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VASP entity '{entity_name}' not found."
        )

    if data.chain is not None:
        vasp.chain = data.chain
    if data.hot_wallet_addresses is not None:
        vasp.hot_wallet_addresses = data.hot_wallet_addresses
    if data.fiu_ind_registered is not None:
        vasp.fiu_ind_registered = data.fiu_ind_registered
    if data.sla_hours is not None:
        vasp.sla_hours = data.sla_hours
    if data.nodal_contact is not None:
        vasp.nodal_contact = data.nodal_contact

    db.commit()
    db.refresh(vasp)

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="VASP_DIRECTORY_UPDATED",
        target_id=entity_name,
    )

    return vasp


@router.delete("/{entity_name}", status_code=status.HTTP_200_OK)
def delete_vasp(
    entity_name: str,
    current_officer: Profile = Depends(check_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    """Delete a VASP directory entry (strictly ADMIN role only)."""
    vasp = db.query(VASPDirectory).filter(VASPDirectory.entity_name == entity_name).first()
    if not vasp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VASP entity '{entity_name}' not found."
        )

    db.delete(vasp)
    db.commit()

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="VASP_DIRECTORY_DELETED",
        target_id=entity_name,
    )

    return {"message": f"VASP entity '{entity_name}' deleted successfully."}
