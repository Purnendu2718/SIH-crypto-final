"""Police Intel Exchange API Router.
Enables privacy-preserving inter-agency intelligence sharing between state cyber cells.
Architecture: Hash-and-RBAC Design.
Explicitly NOT a zero-knowledge-proof (ZKP) system: Officers hash suspect addresses client-side
via SHA-256 before submission or lookup. The exchange stores strictly the digest + typology tag + district.
Raw blockchain addresses and victim PII are NEVER submitted or stored.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import re
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import IntelTag, Profile, utc_now
from app.schemas import (
    IntelTagSubmit,
    IntelLookupRequest,
    IntelLookupResponse,
    IntelTagOut,
)
from app.security import get_current_officer
from app.services.audit import append_audit_entry

router = APIRouter(prefix="/api/intel", tags=["Police Intel Exchange (Hash-and-RBAC)"])

HEX_64_REGEX = re.compile(r"^[a-fA-F0-9]{64}$")


@router.post("/submit", response_model=IntelTagOut, status_code=status.HTTP_201_CREATED)
def submit_intel_tag(
    data: IntelTagSubmit,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Submit an anonymized SHA-256 digest of a suspect address to the Police Intel Exchange.
    Explicit privacy guarantee: Raw wallet addresses and victim PII are NEVER accepted.
    """
    clean_hash = data.address_hash.strip().lower()

    # Enforce strict 64-character SHA-256 hex digest format
    if not HEX_64_REGEX.match(clean_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid address_hash: must be a 64-character hexadecimal SHA-256 digest. Raw addresses are prohibited."
        )

    existing = db.query(IntelTag).filter(IntelTag.address_hash == clean_hash).first()
    if existing:
        # Update existing tag if district / tag updated
        existing.tag = data.tag.upper().strip()
        existing.district = data.district.strip()
        existing.submitted_by = current_officer.id
        existing.submitted_at = utc_now()
        db.commit()
        db.refresh(existing)
        tag_obj = existing
    else:
        new_tag = IntelTag(
            address_hash=clean_hash,
            tag=data.tag.upper().strip(),
            district=data.district.strip(),
            submitted_by=current_officer.id,
            submitted_at=utc_now(),
        )
        db.add(new_tag)
        db.commit()
        db.refresh(new_tag)
        tag_obj = new_tag

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="POLICE_INTEL_TAG_SUBMITTED",
        target_id=clean_hash,
    )

    return IntelTagOut(
        address_hash=tag_obj.address_hash,
        tag=tag_obj.tag,
        district=tag_obj.district,
        submitted_by=tag_obj.submitted_by,
        submitted_at=tag_obj.submitted_at,
    )


@router.post("/lookup", response_model=IntelLookupResponse)
def lookup_intel_hash(
    data: IntelLookupRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Query the Police Intel Exchange using a client-computed SHA-256 hash.
    Explicitly a Hash-and-RBAC design: returns matched tags only to authenticated law enforcement officers.
    """
    clean_hash = data.address_hash.strip().lower()

    if not HEX_64_REGEX.match(clean_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid address_hash: query must be a valid 64-character SHA-256 hexadecimal digest."
        )

    records = db.query(IntelTag).filter(IntelTag.address_hash == clean_hash).all()

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="POLICE_INTEL_LOOKUP_PERFORMED",
        target_id=clean_hash,
    )

    tags_out = [
        {
            "tag": r.tag,
            "district": r.district,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        }
        for r in records
    ]

    return IntelLookupResponse(
        match_found=len(tags_out) > 0,
        address_hash=clean_hash,
        tags=tags_out,
        architecture_notice=(
            "Hash-and-RBAC architecture: Query verified against SHA-256 digests. "
            "Raw address and victim PII never transmitted or stored."
        ),
    )
