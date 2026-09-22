#!/usr/bin/env python3
"""CryptoTrace Sentinel — Automated Notice Follow-up & Overdue Reminders Scheduler.
Scans for sent statutory notices whose reply deadline has elapsed and generates
DRAFT reminder notices for officer review.
CRITICAL: Reminders are NEVER auto-dispatched.
Reference: Phase 10 — Notice and email drafter with approval workflow, SIH26183.
"""

import sys
import os
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
sys.path.insert(0, str(backend_dir))

from app.database import SessionLocal, init_db
from app.services.notice_service import check_and_create_overdue_reminders


def main():
    print("==================================================================")
    print("[*] CryptoTrace Sentinel — Follow-up Notice Scanner")
    print("[*] Checking for overdue statutory requisitions...")
    print("==================================================================")

    init_db()
    db = SessionLocal()
    try:
        created = check_and_create_overdue_reminders(db)
        print(f"[+] Scan completed successfully.")
        print(f"[+] Overdue notices processed: {len(created)}")
        for r in created:
            print(f"    - Draft Reminder: ID={r.id} | Case={r.case_id} | Recipient={r.recipient_email} | Status={r.status}")
        if not created:
            print("[+] No overdue notices requiring follow-up reminders.")
    except Exception as e:
        print(f"[!] Error running follow-up scanner: {e}")
        sys.exit(1)
    finally:
        db.close()

    print("==================================================================\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
