"""Tamper-Evident Hash-Chained Audit Log Service.
Every case/evidence/notice write action is cryptographically appended to a hash chain.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import AuditLog, generate_uuid, utc_now

GENESIS_HASH = "0" * 64


def format_canonical_timestamp(ts: Any) -> str:
    """Format timestamp into a strictly canonical string across database engines."""
    if isinstance(ts, str):
        ts = ts.replace(" ", "T")
        if "+" in ts:
            ts = ts.split("+")[0]
        elif ts.endswith("Z"):
            ts = ts[:-1]
        return ts
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return str(ts)


def compute_entry_hash(
    prev_hash: str,
    action: str,
    officer_id: str,
    target_id: Optional[str],
    timestamp_str: str,
) -> str:
    """Compute cryptographic SHA-256 entry hash linking to preceding entry."""
    canonical_payload = f"{prev_hash}:{action}:{officer_id}:{target_id or ''}:{timestamp_str}"
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def append_audit_entry(
    db: Session,
    officer_id: str,
    action: str,
    target_id: Optional[str] = None,
) -> AuditLog:
    """Append a new action to the hash-chained audit log.
    Ensures every write is linked to the prior block's hash.
    """
    # Fetch the most recent audit entry to establish previous hash
    last_entry = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
    prev_hash = last_entry.entry_hash if last_entry else GENESIS_HASH

    ts = utc_now()
    ts_str = format_canonical_timestamp(ts)

    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        action=action,
        officer_id=officer_id,
        target_id=target_id,
        timestamp_str=ts_str,
    )

    entry = AuditLog(
        entry_id=generate_uuid(),
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        officer_id=officer_id,
        action=action,
        target_id=target_id,
        timestamp=ts,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def verify_audit_chain(db: Session) -> Dict[str, Any]:
    """Verify the integrity of the entire audit chain.
    Recomputes hashes in sequence to detect any unauthorized database tampering.
    """
    entries = db.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()

    if not entries:
        return {
            "is_valid": True,
            "total_entries": 0,
            "status": "CHAIN_EMPTY",
            "message": "Audit chain is empty. No entries recorded.",
        }

    expected_prev = GENESIS_HASH

    for idx, entry in enumerate(entries):
        # 1. Check prev_hash link
        if entry.prev_hash != expected_prev:
            return {
                "is_valid": False,
                "status": "PREV_HASH_MISMATCH",
                "corrupted_entry_index": idx,
                "corrupted_entry_id": entry.entry_id,
                "action": entry.action,
                "expected_prev_hash": expected_prev,
                "found_prev_hash": entry.prev_hash,
                "message": f"Tampering detected at entry {idx} (ID: {entry.entry_id}): Broken previous hash pointer.",
            }

        # 2. Recompute entry hash
        ts_str = format_canonical_timestamp(entry.timestamp)
        recomputed_hash = compute_entry_hash(
            prev_hash=entry.prev_hash,
            action=entry.action,
            officer_id=entry.officer_id,
            target_id=entry.target_id,
            timestamp_str=ts_str,
        )

        if entry.entry_hash != recomputed_hash:
            return {
                "is_valid": False,
                "status": "HASH_TAMPERED",
                "corrupted_entry_index": idx,
                "corrupted_entry_id": entry.entry_id,
                "action": entry.action,
                "expected_hash": recomputed_hash,
                "found_hash": entry.entry_hash,
                "message": f"Tampering detected at entry {idx} (ID: {entry.entry_id}): Recalculated hash does not match stored hash.",
            }

        expected_prev = entry.entry_hash

    return {
        "is_valid": True,
        "total_entries": len(entries),
        "status": "CHAIN_INTACT",
        "latest_hash": expected_prev,
        "message": f"Audit chain verified successfully across {len(entries)} entries. Zero tampering detected.",
    }
