"""CLI script to bulk-ingest GraphSense TagPacks and ActorPacks into the local database.
Usage:
    python scripts/ingest_graphsense_tagpacks.py [--offline-only] [--limit-packs N] [--source-zip PATH]
"""

import sys
import os
import argparse

# Add parent directory to sys.path so app modules can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, init_db
from app.services.tagpack_ingest import ingest_tagpacks_and_actors


def main():
    parser = argparse.ArgumentParser(description="Ingest GraphSense TagPacks into CryptoTrace Sentinel database")
    parser.add_argument("--offline-only", action="store_true", help="Force ingestion from offline seed file only")
    parser.add_argument("--limit-packs", type=int, default=None, help="Limit number of YAML packs to process (for rapid testing)")
    parser.add_argument("--source-zip", type=str, default=None, help="Path to local repository zip archive")

    args = parser.parse_args()

    print("==================================================================")
    print("  CryptoTrace Sentinel — GraphSense TagPacks Bulk Ingestion Tool")
    print("==================================================================")

    init_db()
    db = SessionLocal()
    try:
        res = ingest_tagpacks_and_actors(
            db=db,
            source_zip=args.source_zip,
            offline_only=args.offline_only,
            limit_packs=args.limit_packs,
        )
        print(f"Status:          {res['status']}")
        print(f"Source:          {res['source']}")
        print(f"Actors Ingested: {res['actors_ingested']}")
        print(f"Labels Ingested: {res['labels_ingested']}")
        print(f"Synced At:       {res['synced_at']}")
        print("Bulk ingestion completed successfully.")
    except Exception as ex:
        print(f"Ingestion failed with error: {ex}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
