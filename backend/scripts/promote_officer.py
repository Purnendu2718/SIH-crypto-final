"""Command-line script to promote an officer profile to SUPERVISOR or ADMIN for testing.
Usage:
    python backend/scripts/promote_officer.py --email officer@sentinel.gov.in --role SUPERVISOR
"""

import sys
import os
import argparse

# Add parent directory to path so app modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal, init_db
from app.models import Profile


def promote(email: str, role: str):
    init_db()
    db = SessionLocal()
    try:
        profile = db.query(Profile).filter(Profile.email == email).first()
        if not profile:
            print(f"Error: Officer with email '{email}' not found.")
            sys.exit(1)

        valid_roles = ["INVESTIGATOR", "SUPERVISOR", "ADMIN"]
        if role not in valid_roles:
            print(f"Error: Role must be one of {valid_roles}")
            sys.exit(1)

        old_role = profile.role
        profile.role = role
        db.commit()
        db.refresh(profile)
        print(f"Success: Officer '{profile.full_name}' ({profile.email}) promoted from '{old_role}' to '{profile.role}'.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Promote an officer profile role.")
    parser.add_argument("--email", required=True, help="Officer email address")
    parser.add_argument("--role", required=True, choices=["INVESTIGATOR", "SUPERVISOR", "ADMIN"], help="New role")
    args = parser.parse_args()

    promote(args.email, args.role)
