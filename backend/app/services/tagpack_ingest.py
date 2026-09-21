"""GraphSense TagPacks and ActorPacks Bulk Ingestion Engine.
Pulls MIT-licensed TagPacks collection from github.com/graphsense/graphsense-tagpacks
and populates entity_labels and entities tables with real exchange, mixer, and DeFi tags.
Reference: SIH26183, Ministry of Home Affairs / I4C — Phase 8E.
"""

import os
import io
import json
import zipfile
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Entity, EntityLabel, TagPackSyncStatus, generate_uuid, utc_now

logger = logging.getLogger("sentinel.tagpack_ingest")

try:
    import yaml
    Loader = yaml.CSafeLoader if hasattr(yaml, "CSafeLoader") else yaml.SafeLoader
except ImportError:
    yaml = None
    Loader = None

GRAPHSENSE_ZIP_URL = "https://github.com/graphsense/graphsense-tagpacks/archive/refs/heads/master.zip"
SEED_FALLBACK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures", "tagpacks_seed.json")


def _parse_iso_or_date(date_val: Any) -> Optional[datetime]:
    if not date_val:
        return None
    if isinstance(date_val, datetime):
        return date_val if date_val.tzinfo else date_val.replace(tzinfo=timezone.utc)
    date_str = str(date_val).strip()
    try:
        # Handles YYYY-MM-DD
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def ingest_from_seed_file(db: Session) -> Dict[str, Any]:
    """Fallback: Ingest curated real-world GraphSense entries from bundled offline seed."""
    if not os.path.exists(SEED_FALLBACK_FILE):
        raise FileNotFoundError(f"Offline seed file not found: {SEED_FALLBACK_FILE}")

    with open(SEED_FALLBACK_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    actors_data = data.get("actors", [])
    labels_data = data.get("labels", [])

    return _persist_records(db=db, actors=actors_data, labels=labels_data, source="OFFLINE_TAGPACKS_SEED")


def _persist_records(
    db: Session,
    actors: List[Dict[str, Any]],
    labels: List[Dict[str, Any]],
    source: str = "GRAPHSENSE_TAGPACK",
) -> Dict[str, Any]:
    """Bulk upsert extracted actors and address labels into SQLite or PostgreSQL."""
    now = utc_now()
    actors_count = 0
    labels_count = 0

    # 1. Upsert Entities / Actors
    existing_entities = {e.actor_id: e for e in db.query(Entity).all()}

    new_entities = []
    for a in actors:
        actor_id = a.get("id") or a.get("actor_id")
        if not actor_id:
            continue
        label = a.get("label") or actor_id
        cats = a.get("categories") or []
        if isinstance(cats, str):
            cats = [cats]
        uri = a.get("uri")
        jurisdictions = a.get("jurisdictions") or []

        if actor_id in existing_entities:
            ent = existing_entities[actor_id]
            ent.label = label
            ent.categories = cats
            ent.uri = uri
            ent.jurisdictions = jurisdictions
            ent.last_updated = now
        else:
            new_ent = Entity(
                id=generate_uuid(),
                actor_id=actor_id,
                label=label,
                categories=cats,
                uri=uri,
                jurisdictions=jurisdictions,
                last_updated=now,
            )
            new_entities.append(new_ent)
            existing_entities[actor_id] = new_ent
        actors_count += 1

    if new_entities:
        db.add_all(new_entities)
    db.flush()

    # 2. Upsert EntityLabels
    # Index existing labels by (address_lower, chain)
    existing_labels = {
        (l.address.lower(), l.chain.upper()): l
        for l in db.query(EntityLabel).all()
    }

    new_labels = []
    for item in labels:
        addr = (item.get("address") or "").strip()
        chain = (item.get("chain") or "BTC").strip().upper()
        lbl = item.get("label") or "Unknown"
        actor_id = item.get("actor_id")
        src_url = item.get("source_url")
        last_mod = _parse_iso_or_date(item.get("last_modified"))
        tag_src = item.get("tag_source") or "GRAPHSENSE_TAGPACK"

        if not addr or addr.lower() in ("0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dead", "0x0"):
            continue

        key = (addr.lower(), chain)
        if key in existing_labels:
            el = existing_labels[key]
            el.label = lbl
            el.actor_id = actor_id
            el.source_url = src_url
            el.last_modified = last_mod
            el.tag_source = tag_src
        else:
            new_el = EntityLabel(
                id=generate_uuid(),
                address=addr,
                chain=chain,
                label=lbl,
                actor_id=actor_id,
                source_url=src_url,
                last_modified=last_mod,
                tag_source=tag_src,
                created_at=now,
            )
            new_labels.append(new_el)
            existing_labels[key] = new_el
        labels_count += 1

    if new_labels:
        db.add_all(new_labels)

    # 3. Record Sync Status
    sync_record = TagPackSyncStatus(
        id=generate_uuid(),
        last_synced_at=now,
        total_actors=actors_count,
        total_labels=labels_count,
        source=source,
        status="COMPLETED",
    )
    db.add(sync_record)
    db.commit()

    logger.info(f"Ingested {actors_count} entities and {labels_count} address labels from {source}.")
    return {
        "status": "COMPLETED",
        "source": source,
        "actors_ingested": actors_count,
        "labels_ingested": labels_count,
        "synced_at": now.isoformat(),
    }


def ingest_tagpacks_and_actors(
    db: Session,
    source_zip: Optional[str] = None,
    offline_only: bool = False,
    limit_packs: Optional[int] = None,
) -> Dict[str, Any]:
    """High-level ingestion pipeline:
    Downloads graphsense-tagpacks master zip, parses actors & packs via CSafeLoader,
    and bulk-persists to database. Falls back seamlessly to offline seed on failure.
    """
    if offline_only:
        logger.info("Offline-only mode requested; loading bundled TagPacks seed.")
        return ingest_from_seed_file(db)

    zip_bytes = None

    if source_zip and os.path.exists(source_zip):
        logger.info(f"Loading TagPacks from local zip archive: {source_zip}")
        with open(source_zip, "rb") as f:
            zip_bytes = f.read()
    else:
        try:
            import httpx
            logger.info(f"Downloading latest TagPacks repository from {GRAPHSENSE_ZIP_URL}...")
            resp = httpx.get(GRAPHSENSE_ZIP_URL, follow_redirects=True, timeout=30.0)
            if resp.status_code == 200:
                zip_bytes = resp.content
                logger.info(f"Downloaded {len(zip_bytes)} bytes from GraphSense repository.")
            else:
                logger.warning(f"Download returned status {resp.status_code}; falling back to offline seed.")
        except Exception as ex:
            logger.warning(f"Network download failed: {ex}. Falling back to offline seed.")

    if not zip_bytes:
        return ingest_from_seed_file(db)

    # Process ZIP in memory
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
        namelist = z.namelist()

        # 1. Parse ActorPack
        actor_files = [n for n in namelist if "actors/" in n and n.endswith(".yaml")]
        actors_list = []
        for af in actor_files:
            try:
                data = yaml.load(z.read(af), Loader=Loader)
                if isinstance(data, dict):
                    actors_list.extend(data.get("actors", []))
            except Exception as e:
                logger.warning(f"Error parsing actorpack {af}: {e}")

        # 2. Parse TagPacks
        pack_files = [n for n in namelist if "/packs/" in n and n.endswith(".yaml")]
        if limit_packs:
            pack_files = pack_files[:limit_packs]

        labels_list = []
        for pf in pack_files:
            try:
                pdata = yaml.load(z.read(pf), Loader=Loader)
                if not isinstance(pdata, dict):
                    continue
                pack_lbl = pdata.get("label") or pdata.get("title") or os.path.basename(pf).replace(".yaml", "")
                pack_actor = pdata.get("actor")
                pack_currency = (pdata.get("currency") or "BTC").upper()
                pack_source = pdata.get("source")
                pack_lastmod = str(pdata.get("lastmod") or "")

                tags = pdata.get("tags", [])
                for t in tags:
                    addr = t.get("address")
                    if not addr:
                        continue
                    labels_list.append({
                        "address": addr,
                        "chain": (t.get("currency") or pack_currency).upper(),
                        "label": t.get("label") or pack_lbl,
                        "actor_id": t.get("actor") or pack_actor,
                        "source_url": t.get("source") or pack_source,
                        "last_modified": str(t.get("lastmod") or pack_lastmod),
                        "tag_source": "GRAPHSENSE_TAGPACK",
                    })
            except Exception as e:
                logger.warning(f"Error parsing pack {pf}: {e}")

        return _persist_records(
            db=db,
            actors=actors_list,
            labels=labels_list,
            source="GITHUB_GRAPHSENSE_TAGPACKS",
        )
    except Exception as ex:
        logger.error(f"Failed parsing repository zip: {ex}. Using offline seed fallback.")
        return ingest_from_seed_file(db)
