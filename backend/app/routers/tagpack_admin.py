"""Admin router for GraphSense TagPacks management and on-demand refresh.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8E.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Profile, TagPackSyncStatus, Entity, EntityLabel
from app.security import require_supervisor_or_admin, require_investigator
from app.services.tagpack_scheduler import refresh_tagpacks_job, should_refresh_tagpacks

router = APIRouter(prefix="", tags=["TagPacks Administration"])


class RefreshResponse(BaseModel):
    status: str
    source: Optional[str] = None
    actors_ingested: Optional[int] = None
    labels_ingested: Optional[int] = None
    synced_at: Optional[str] = None
    message: Optional[str] = None


@router.get("/api/v1/admin/tagpacks/status")
@router.get("/api/admin/tagpacks/status")
def get_tagpack_status(
    officer: Profile = Depends(require_investigator),
    db: Session = Depends(get_db),
):
    """Retrieve current GraphSense TagPacks coverage and synchronization status."""
    latest_sync = (
        db.query(TagPackSyncStatus)
        .order_by(TagPackSyncStatus.last_synced_at.desc())
        .first()
    )
    total_entities = db.query(Entity).count()
    total_labels = db.query(EntityLabel).count()
    refresh_needed = should_refresh_tagpacks(db)

    return {
        "total_entities": total_entities,
        "total_labels": total_labels,
        "refresh_recommended": refresh_needed,
        "latest_sync": {
            "id": latest_sync.id,
            "last_synced_at": latest_sync.last_synced_at.isoformat(),
            "source": latest_sync.source,
            "status": latest_sync.status,
            "total_actors": latest_sync.total_actors,
            "total_labels": latest_sync.total_labels,
        } if latest_sync else None,
    }


@router.post("/api/v1/admin/tagpacks/refresh", response_model=RefreshResponse)
@router.post("/api/admin/tagpacks/refresh", response_model=RefreshResponse)
def trigger_tagpack_refresh(
    force: bool = Query(True, description="Force re-download regardless of refresh interval"),
    limit_packs: Optional[int] = Query(None, description="Optional pack limit for rapid testing"),
    officer: Profile = Depends(require_supervisor_or_admin),
    db: Session = Depends(get_db),
):
    """Trigger an on-demand TagPacks re-download and upsert."""
    res = refresh_tagpacks_job(
        db=db,
        force=force,
        limit_packs=limit_packs,
    )
    return RefreshResponse(
        status=res.get("status", "COMPLETED"),
        source=res.get("source"),
        actors_ingested=res.get("actors_ingested"),
        labels_ingested=res.get("labels_ingested"),
        synced_at=res.get("synced_at") or res.get("last_synced_at"),
        message=res.get("message"),
    )
