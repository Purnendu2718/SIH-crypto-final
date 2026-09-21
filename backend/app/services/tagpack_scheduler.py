"""Scheduled Refresh Worker for GraphSense TagPacks and ActorPacks.
Periodically re-pulls the latest public TagPacks/ActorPacks from GitHub
and upserts entity_labels and entities tables so forensic coverage stays up to date.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8E.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TagPackSyncStatus, utc_now
from app.services.tagpack_ingest import ingest_tagpacks_and_actors

logger = logging.getLogger("sentinel.tagpack_scheduler")


def should_refresh_tagpacks(db: Session, max_age_days: Optional[int] = None) -> bool:
    """Check if the latest TagPack sync is older than the configured refresh interval."""
    interval_days = max_age_days or settings.TAGPACK_REFRESH_INTERVAL_DAYS
    latest_sync = (
        db.query(TagPackSyncStatus)
        .order_by(TagPackSyncStatus.last_synced_at.desc())
        .first()
    )
    if not latest_sync:
        return True

    now = utc_now()
    cutoff = now - timedelta(days=interval_days)
    sync_time = latest_sync.last_synced_at
    if sync_time.tzinfo is None:
        sync_time = sync_time.replace(tzinfo=timezone.utc)

    return sync_time < cutoff


def refresh_tagpacks_job(
    db: Session,
    force: bool = False,
    source_zip: Optional[str] = None,
    limit_packs: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute scheduled or on-demand TagPacks refresh.
    If force=False and data is fresh, skips downloading to conserve bandwidth and API rate limits.
    """
    if not force and not should_refresh_tagpacks(db):
        latest = (
            db.query(TagPackSyncStatus)
            .order_by(TagPackSyncStatus.last_synced_at.desc())
            .first()
        )
        logger.info("TagPacks dataset is fresh; skipping scheduled refresh.")
        return {
            "status": "SKIPPED_FRESH",
            "message": f"TagPacks were refreshed recently on {latest.last_synced_at.isoformat() if latest else 'N/A'}.",
            "last_synced_at": latest.last_synced_at.isoformat() if latest else None,
            "total_actors": latest.total_actors if latest else 0,
            "total_labels": latest.total_labels if latest else 0,
        }

    logger.info("Starting scheduled GraphSense TagPacks and ActorPacks refresh...")
    try:
        result = ingest_tagpacks_and_actors(
            db=db,
            source_zip=source_zip,
            limit_packs=limit_packs,
        )
        logger.info(f"TagPacks refresh completed: {result['actors_ingested']} actors, {result['labels_ingested']} labels.")
        return result
    except Exception as ex:
        logger.error(f"Scheduled TagPacks refresh failed: {ex}")
        return {
            "status": "FAILED",
            "error": str(ex),
            "synced_at": utc_now().isoformat(),
        }
