"""Standalone verification script template for evidence packages.
Reference: Phase 7 — Evidence package, report and integrity verification.
Standard library only: os, sys, hashlib, json.
"""

VERIFY_SCRIPT_CONTENT = '''#!/usr/bin/env python3
"""
CryptoTrace Sentinel — Forensic Evidence Package Integrity Verifier
Verifies cryptographic SHA-256 checksums in MANIFEST.json and audit log hash-chain integrity.
Standard Library Only.
"""

import os
import sys
import json
import hashlib


def format_canonical_timestamp(ts):
    """Normalize timestamp string into canonical format for hash verification."""
    if not ts:
        return ""
    ts_str = str(ts).strip().replace(" ", "T")
    if "+" in ts_str:
        ts_str = ts_str.split("+")[0]
    elif ts_str.endswith("Z"):
        ts_str = ts_str[:-1]
    return ts_str


def compute_entry_hash(prev_hash, action, officer_id, target_id, timestamp_str):
    """Recompute audit log entry hash."""
    canonical = f"{prev_hash}:{action}:{officer_id}:{target_id or ''}:{timestamp_str}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_file_sha256(filepath):
    """Compute SHA-256 of file in 64KB chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_package(root_dir="."):
    print("=================================================================")
    print(" CRYPTOTRACE SENTINEL — EVIDENCE PACKAGE INTEGRITY VERIFIER")
    print("=================================================================")
    manifest_path = os.path.join(root_dir, "MANIFEST.json")
    if not os.path.isfile(manifest_path):
        print(f"FAIL: Manifest not found at {manifest_path}")
        return 1

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        print(f"FAIL: Unable to parse MANIFEST.json: {e}")
        return 1

    files_declared = manifest.get("files", {})
    if not files_declared:
        print("FAIL: MANIFEST.json contains no file declarations.")
        return 1

    print(f"[*] Verifying {len(files_declared)} files against MANIFEST.json...")

    for rel_path, meta in sorted(files_declared.items()):
        full_path = os.path.join(root_dir, rel_path)
        if not os.path.isfile(full_path):
            print(f"FAIL: Missing file declared in manifest: {rel_path}")
            return 1

        expected_size = meta.get("size")
        actual_size = os.path.getsize(full_path)
        if expected_size is not None and actual_size != expected_size:
            print(f"FAIL: Size mismatch for {rel_path}: expected {expected_size} bytes, got {actual_size} bytes")
            return 1

        expected_hash = meta.get("sha256")
        actual_hash = compute_file_sha256(full_path)
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            print(f"FAIL: Hash mismatch for {rel_path}:")
            print(f"  Expected SHA-256: {expected_hash}")
            print(f"  Computed SHA-256: {actual_hash}")
            return 1

    print("[+] All files in MANIFEST.json matched expected SHA-256 checksums.")

    # Verify audit excerpt hash chain
    audit_path = os.path.join(root_dir, "audit_excerpt.json")
    if os.path.isfile(audit_path):
        print("[*] Verifying audit_excerpt.json cryptographic hash chain...")
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                audit_data = json.load(f)
        except Exception as e:
            print(f"FAIL: Unable to parse audit_excerpt.json: {e}")
            return 1

        entries = audit_data.get("entries", [])
        if not entries and isinstance(audit_data, list):
            entries = audit_data

        for idx, entry in enumerate(entries):
            entry_id = entry.get("entry_id", f"idx_{idx}")
            prev_hash = entry.get("prev_hash")
            stored_hash = entry.get("entry_hash")
            action = entry.get("action", "")
            officer_id = entry.get("officer_id", "")
            target_id = entry.get("target_id")
            raw_ts = entry.get("timestamp", "")
            ts_str = format_canonical_timestamp(raw_ts)

            # Linkage check
            if idx > 0:
                prev_entry_hash = entries[idx - 1].get("entry_hash")
                if prev_hash != prev_entry_hash:
                    print(f"FAIL: Audit chain linkage broken at entry {idx} ({entry_id}):")
                    print(f"  Expected prev_hash: {prev_entry_hash}")
                    print(f"  Found prev_hash:    {prev_hash}")
                    return 1

            # Recalculate entry hash
            recomputed = compute_entry_hash(
                prev_hash=prev_hash or ("0" * 64),
                action=action,
                officer_id=officer_id,
                target_id=target_id,
                timestamp_str=ts_str,
            )

            if stored_hash and recomputed.lower() != stored_hash.lower():
                print(f"FAIL: Audit row tampering detected at entry {idx} ({entry_id}):")
                print(f"  Expected entry_hash: {recomputed}")
                print(f"  Stored entry_hash:   {stored_hash}")
                return 1

        print(f"[+] Audit excerpt hash chain intact across {len(entries)} recorded actions.")

    print("=================================================================")
    print("PASS: Evidence package integrity verified. Zero tampering detected.")
    print("=================================================================")
    return 0


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    code = verify_package(target)
    sys.exit(code)
'''
