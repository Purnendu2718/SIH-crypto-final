"""Evidence Package Generation and Merkle Tree Cryptographic Accounting.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import EvidencePackage, generate_uuid, utc_now


def compute_sha256(content: bytes) -> str:
    """Compute standard SHA-256 hash of bytes content."""
    return hashlib.sha256(content).hexdigest()


def compute_merkle_root(leaf_hashes: List[str]) -> str:
    """Compute canonical binary Merkle root from a list of SHA-256 leaf hashes.
    If 0 leaves, returns empty hash. If 1 leaf, returns that leaf.
    """
    if not leaf_hashes:
        return "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # SHA-256 of empty string
    if len(leaf_hashes) == 1:
        return leaf_hashes[0]

    current_level = list(leaf_hashes)
    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            # Duplicate the last hash if odd number of leaves (Bitcoin/RFC 6962 standard)
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            combined = (left + right).encode("utf-8")
            parent_hash = hashlib.sha256(combined).hexdigest()
            next_level.append(parent_hash)
        current_level = next_level

    return current_level[0]


class EvidenceManager:
    """Manages court-ready cryptographic evidence packages and hashes."""

    @staticmethod
    def serialize_trace_payload(payload: Dict[str, Any]) -> bytes:
        """Deterministically serialize payload to bytes with sorted keys for consistent hashing."""
        return json.dumps(payload, sort_keys=True, indent=2, default=str).encode("utf-8")

    @staticmethod
    def create_evidence_package(
        run_id: str,
        trace_payload: Dict[str, Any],
        additional_files: Optional[Dict[str, bytes]] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Create a cryptographic evidence package.
        Computes SHA-256 of serialized raw trace, Merkle root across all package files,
        and records to evidence_packages database table.
        """
        raw_json_bytes = EvidenceManager.serialize_trace_payload(trace_payload)
        json_hash = compute_sha256(raw_json_bytes)

        # Build file hashes dictionary
        file_hashes: Dict[str, str] = {
            "trace_payload.json": json_hash,
        }

        if additional_files:
            for filename, file_bytes in additional_files.items():
                file_hashes[filename] = compute_sha256(file_bytes)

        # Compute Merkle root across all files
        sorted_leaf_hashes = [file_hashes[k] for k in sorted(file_hashes.keys())]
        merkle_root = compute_merkle_root(sorted_leaf_hashes)

        package_id = generate_uuid()
        timestamp = utc_now()

        # Write to database if session provided
        if db is not None:
            package_record = EvidencePackage(
                package_id=package_id,
                run_id=run_id,
                sha256_hash=json_hash,
                merkle_root=merkle_root,
                generated_at=timestamp,
            )
            db.add(package_record)
            db.commit()

        return {
            "package_id": package_id,
            "run_id": run_id,
            "sha256_hash": json_hash,
            "merkle_root": merkle_root,
            "generated_at": timestamp.isoformat(),
            "files": file_hashes,
        }
