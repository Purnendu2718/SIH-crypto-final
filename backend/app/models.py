"""SQLAlchemy database models for CryptoTrace Sentinel.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Numeric,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Text,
)
from sqlalchemy.orm import relationship
from app.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class Profile(Base):
    """Officer profile keyed to Supabase auth.users or local credentials."""
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=True)  # For pure-local offline dev
    full_name = Column(String, nullable=False)
    badge_no = Column(String, nullable=True)
    role = Column(String, nullable=False, default="INVESTIGATOR")  # INVESTIGATOR, SUPERVISOR, ADMIN
    district = Column(String, nullable=True, default="Central")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    cases = relationship("Case", back_populates="assigned_officer")
    audit_entries = relationship("AuditLog", back_populates="officer")


class Case(Base):
    """Cybercrime complaint case record."""
    __tablename__ = "cases"

    case_id = Column(String, primary_key=True, default=generate_uuid)
    ncrp_ref = Column(String, index=True, nullable=True)
    victim_utr = Column(String, nullable=True)
    victim_utr_timestamp = Column(DateTime(timezone=True), nullable=True)
    amount_inr = Column(Numeric, nullable=True)
    assigned_officer_id = Column(String, ForeignKey("profiles.id"), nullable=True)
    status = Column(String, default="OPEN")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    assigned_officer = relationship("Profile", back_populates="cases")
    wallet_submissions = relationship("WalletSubmission", back_populates="case", cascade="all, delete-orphan")
    watchlist_entries = relationship("WatchlistEntry", back_populates="case", cascade="all, delete-orphan")


class WalletSubmission(Base):
    """Suspect wallet submitted by victim or investigating officer."""
    __tablename__ = "wallet_submissions"

    submission_id = Column(String, primary_key=True, default=generate_uuid)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False)
    chain = Column(String, nullable=False, default="ETH")
    address = Column(String, nullable=False)
    submitted_at = Column(DateTime(timezone=True), default=utc_now)

    case = relationship("Case", back_populates="wallet_submissions")
    analysis_runs = relationship("AnalysisRun", back_populates="submission", cascade="all, delete-orphan")


class AnalysisRun(Base):
    """Automated multi-hop trace execution session."""
    __tablename__ = "analysis_runs"

    run_id = Column(String, primary_key=True, default=generate_uuid)
    submission_id = Column(String, ForeignKey("wallet_submissions.submission_id"), nullable=False)
    _status = Column("status", String, default="PENDING")
    started_at = Column(DateTime(timezone=True), default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def status(self):
        from app.services.trace_engine import ForensicStatus
        return ForensicStatus(self._status) if self._status else self._status

    @status.setter
    def status(self, value):
        self._status = str(value) if value is not None else value

    submission = relationship("WalletSubmission", back_populates="analysis_runs")
    trace_paths = relationship("TracePath", back_populates="run", cascade="all, delete-orphan")
    attributions = relationship("Attribution", back_populates="run", cascade="all, delete-orphan")
    typologies = relationship("TypologyDetected", back_populates="run", cascade="all, delete-orphan")
    evidence_packages = relationship("EvidencePackage", back_populates="run", cascade="all, delete-orphan")


class TracePath(Base):
    """Hop-by-hop transaction trace segment."""
    __tablename__ = "trace_paths"

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("analysis_runs.run_id"), nullable=False)
    hop_index = Column(Integer, nullable=False)
    from_addr = Column(String, nullable=False)
    to_addr = Column(String, nullable=False)
    tx_hash = Column(String, nullable=True)
    chain = Column(String, nullable=False, default="ETH")
    value = Column(Numeric, nullable=True)
    confirmations = Column(Integer, nullable=True)
    low_confirmation = Column(Boolean, nullable=True, default=False)

    run = relationship("AnalysisRun", back_populates="trace_paths")


class Attribution(Base):
    """Destination VASP attribution with rule match and confidence band."""
    __tablename__ = "attributions"

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("analysis_runs.run_id"), nullable=False)
    matched_entity = Column(String, nullable=False)
    rule_fired = Column(String, nullable=False)
    confidence = Column(Numeric, nullable=False)  # 0.0 to 1.0
    entity_category = Column(String, nullable=True)  # Phase 8E: exchange, mixing_service, defi, etc.
    score_breakdown = Column(JSON, nullable=True)

    run = relationship("AnalysisRun", back_populates="attributions")


class TypologyDetected(Base):
    """Money laundering typologies flagged along the path."""
    __tablename__ = "typologies_detected"

    id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("analysis_runs.run_id"), nullable=False)
    typology = Column(String, nullable=False)  # FAN_OUT, PEELING_CHAIN, MIXER, LAYERING
    hop_start = Column(Integer, nullable=True)
    hop_end = Column(Integer, nullable=True)

    run = relationship("AnalysisRun", back_populates="typologies")


class EvidencePackage(Base):
    """Court-ready cryptographic evidence package."""
    __tablename__ = "evidence_packages"

    package_id = Column(String, primary_key=True, default=generate_uuid)
    run_id = Column(String, ForeignKey("analysis_runs.run_id"), nullable=False)
    sha256_hash = Column(String, nullable=False)
    merkle_root = Column(String, nullable=True)
    generated_at = Column(DateTime(timezone=True), default=utc_now)

    run = relationship("AnalysisRun", back_populates="evidence_packages")


class AuditLog(Base):
    """Tamper-evident, hash-chained activity audit log."""
    __tablename__ = "audit_log"

    entry_id = Column(String, primary_key=True, default=generate_uuid)
    prev_hash = Column(String, nullable=True)
    entry_hash = Column(String, nullable=False)
    officer_id = Column(String, ForeignKey("profiles.id"), nullable=False)
    action = Column(String, nullable=False)
    target_id = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now)

    officer = relationship("Profile", back_populates="audit_entries")


class VASPDirectory(Base):
    """FIU-IND registered and known exchanges directory."""
    __tablename__ = "vasp_directory"

    entity_name = Column(String, primary_key=True)
    chain = Column(String, nullable=True)
    hot_wallet_addresses = Column(JSON, nullable=True)  # List of addresses
    fiu_ind_registered = Column(Boolean, default=False)
    sla_hours = Column(Numeric, default=24)
    nodal_contact = Column(String, nullable=True)


class WatchlistEntry(Base):
    """Golden Hour monitoring alerts for suspect addresses."""
    __tablename__ = "watchlist_entries"

    id = Column(String, primary_key=True, default=generate_uuid)
    address = Column(String, nullable=False)
    chain = Column(String, nullable=False, default="ETH")
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False)
    alert_channel = Column(String, nullable=True)  # e.g. "TELEGRAM", "WEBHOOK"
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="ACTIVE")  # ACTIVE, TRIGGERED, PAUSED
    last_alert_at = Column(DateTime(timezone=True), nullable=True)
    last_seen_tx_hash = Column(String, nullable=True)

    case = relationship("Case", back_populates="watchlist_entries")


class IntelTag(Base):
    """Anonymized address hash for Police Intel Exchange."""
    __tablename__ = "intel_tags"

    address_hash = Column(String, primary_key=True)
    tag = Column(String, nullable=False)
    district = Column(String, nullable=False)
    submitted_by = Column(String, ForeignKey("profiles.id"), nullable=False)
    submitted_at = Column(DateTime(timezone=True), default=utc_now)


class SanctionsList(Base):
    """OFAC SDN and international sanctions designated cryptocurrency addresses."""
    __tablename__ = "sanctions_list"

    id = Column(String, primary_key=True, default=generate_uuid)
    address = Column(String, nullable=False, index=True)
    chain = Column(String, nullable=True)  # ETH, BTC, TRON, etc.
    program = Column(String, nullable=True)  # CYBER2, DPRK, RUSSIA-EO14024, etc.
    entity_name = Column(String, nullable=False)  # e.g. Lazarus Group, Tornado.Cash
    source = Column(String, default="OFAC_SDN_ADVANCED")
    last_updated = Column(DateTime(timezone=True), default=utc_now)


class Entity(Base):
    """Organization/Actor metadata from GraphSense ActorPacks or live lookups."""
    __tablename__ = "entities"

    id = Column(String, primary_key=True, default=generate_uuid)
    actor_id = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, nullable=False)
    categories = Column(JSON, default=list)  # e.g. ["exchange"], ["mixing_service"], ["defi_dex"], etc.
    uri = Column(String, nullable=True)
    jurisdictions = Column(JSON, default=list)
    last_updated = Column(DateTime(timezone=True), default=utc_now)

    labels = relationship("EntityLabel", back_populates="entity")


class EntityLabel(Base):
    """Cryptocurrency address attribution label from GraphSense TagPacks or live lookup."""
    __tablename__ = "entity_labels"

    id = Column(String, primary_key=True, default=generate_uuid)
    address = Column(String, nullable=False, index=True)
    chain = Column(String, nullable=False, index=True)  # BTC, ETH, TRON, etc.
    label = Column(String, nullable=False)
    actor_id = Column(String, ForeignKey("entities.actor_id"), nullable=True, index=True)
    source_url = Column(String, nullable=True)
    last_modified = Column(DateTime(timezone=True), nullable=True)
    tag_source = Column(String, default="GRAPHSENSE_TAGPACK")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    entity = relationship("Entity", back_populates="labels")


class TagPackSyncStatus(Base):
    """Tracks GraphSense TagPack synchronization status and counts."""
    __tablename__ = "tagpack_sync_status"

    id = Column(String, primary_key=True, default=generate_uuid)
    last_synced_at = Column(DateTime(timezone=True), default=utc_now)
    total_actors = Column(Integer, default=0)
    total_labels = Column(Integer, default=0)
    source = Column(String, default="GITHUB_GRAPHSENSE_TAGPACKS")
    status = Column(String, default="COMPLETED")  # COMPLETED, FAILED, RUNNING
    error_message = Column(String, nullable=True)
