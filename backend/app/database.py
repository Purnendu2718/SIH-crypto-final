"""Database connection, session management, and table initialization."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Configure SQLite or PostgreSQL connection arguments
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Ensure database tables exist in the current database."""
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Automatically add missing columns for existing SQLite databases
    if settings.DATABASE_URL.startswith("sqlite"):
        from sqlalchemy import text
        with engine.connect() as conn:
            # cases table
            try:
                cases_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(cases)")).fetchall()]
                if "victim_utr_timestamp" not in cases_cols:
                    conn.execute(text("ALTER TABLE cases ADD COLUMN victim_utr_timestamp DATETIME"))
                    conn.commit()
            except Exception:
                pass

            # watchlist_entries table
            try:
                wl_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(watchlist_entries)")).fetchall()]
                if "created_at" not in wl_cols:
                    conn.execute(text("ALTER TABLE watchlist_entries ADD COLUMN created_at DATETIME"))
                if "last_checked_at" not in wl_cols:
                    conn.execute(text("ALTER TABLE watchlist_entries ADD COLUMN last_checked_at DATETIME"))
                if "status" not in wl_cols:
                    conn.execute(text("ALTER TABLE watchlist_entries ADD COLUMN status TEXT DEFAULT 'ACTIVE'"))
                if "last_alert_at" not in wl_cols:
                    conn.execute(text("ALTER TABLE watchlist_entries ADD COLUMN last_alert_at DATETIME"))
                if "last_seen_tx_hash" not in wl_cols:
                    conn.execute(text("ALTER TABLE watchlist_entries ADD COLUMN last_seen_tx_hash TEXT"))
                conn.commit()
            except Exception:
                pass

            # trace_paths table (Phase 8: confirmations and low_confirmation)
            try:
                tp_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(trace_paths)")).fetchall()]
                if "confirmations" not in tp_cols:
                    conn.execute(text("ALTER TABLE trace_paths ADD COLUMN confirmations INTEGER"))
                if "low_confirmation" not in tp_cols:
                    conn.execute(text("ALTER TABLE trace_paths ADD COLUMN low_confirmation BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception:
                pass

            # attributions table (Phase 8E: entity_category)
            try:
                attr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(attributions)")).fetchall()]
                if "entity_category" not in attr_cols:
                    conn.execute(text("ALTER TABLE attributions ADD COLUMN entity_category TEXT"))
                conn.commit()
            except Exception:
                pass


# Initialize DB on import if using local SQLite
init_db()

