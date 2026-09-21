"""Seed VASP directory and fixture data into database.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.database import SessionLocal, init_db
from app.models import VASPDirectory
from app.services.adapters.fixture_adapter import FixtureAdapter


def seed_vasp_directory():
    """Seed the database vasp_directory table from demo_dataset.json."""
    init_db()
    db = SessionLocal()
    adapter = FixtureAdapter()
    vasp_list = adapter.get_vasp_directory()

    seeded_count = 0
    try:
        for item in vasp_list:
            existing = db.query(VASPDirectory).filter(VASPDirectory.entity_name == item["entity_name"]).first()
            if not existing:
                vasp = VASPDirectory(
                    entity_name=item["entity_name"],
                    chain=item.get("chain", "ETH"),
                    hot_wallet_addresses=item.get("hot_wallet_addresses", []),
                    fiu_ind_registered=item.get("fiu_ind_registered", False),
                    sla_hours=item.get("sla_hours", 24),
                    nodal_contact=item.get("nodal_contact"),
                )
                db.add(vasp)
                seeded_count += 1
            else:
                # Update addresses and metadata
                existing.hot_wallet_addresses = item.get("hot_wallet_addresses", [])
                existing.fiu_ind_registered = item.get("fiu_ind_registered", False)
                existing.sla_hours = item.get("sla_hours", 24)
                existing.nodal_contact = item.get("nodal_contact")

        db.commit()
        print(f"Successfully seeded/updated {len(vasp_list)} Indian VASPs in database.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_vasp_directory()
