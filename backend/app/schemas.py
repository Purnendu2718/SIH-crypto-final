"""Pydantic schemas for request/response serialization.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str


# ==============================================================================
# Authentication & Officer Profile Schemas
# ==============================================================================

class OfficerSignup(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    badge_no: Optional[str] = "N/A"
    district: Optional[str] = "Central"


class OfficerLogin(BaseModel):
    email: EmailStr
    password: str


class ProfileOut(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: str
    badge_no: Optional[str] = None
    role: str  # INVESTIGATOR, SUPERVISOR, ADMIN
    district: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    officer: ProfileOut


class RoleUpdate(BaseModel):
    email: str
    role: str  # INVESTIGATOR, SUPERVISOR, ADMIN


# ==============================================================================
# Case & Caseload Preload Schemas
# ==============================================================================

class CaseCreate(BaseModel):
    ncrp_ref: Optional[str] = None
    victim_utr: Optional[str] = None
    victim_utr_timestamp: Optional[datetime] = None
    amount_inr: Optional[float] = None
    chain: Optional[str] = "ETH"
    suspect_address: Optional[str] = None


class AttributionSummary(BaseModel):
    id: str
    matched_entity: str
    rule_fired: str
    confidence: float
    score_breakdown: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class AnalysisRunSummary(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    attributions: List[AttributionSummary] = []

    model_config = ConfigDict(from_attributes=True)


class WalletSubmissionSummary(BaseModel):
    submission_id: str
    chain: str
    address: str
    submitted_at: datetime
    analysis_runs: List[AnalysisRunSummary] = []

    model_config = ConfigDict(from_attributes=True)


class CaseOut(BaseModel):
    case_id: str
    ncrp_ref: Optional[str] = None
    victim_utr: Optional[str] = None
    victim_utr_timestamp: Optional[datetime] = None
    amount_inr: Optional[float] = None
    assigned_officer_id: Optional[str] = None
    assigned_officer_name: Optional[str] = None
    status: str
    created_at: datetime
    submissions: List[WalletSubmissionSummary] = []
    latest_entity: Optional[str] = None
    latest_confidence: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Phase 7 — UPI-UTR Correlator Schemas
# ==============================================================================

class UTRCandidateMatch(BaseModel):
    tx_hash: str
    chain: str
    from_address: str
    to_address: str
    tx_timestamp: datetime
    value: float
    value_inr: Optional[float] = None
    time_diff_minutes: float
    amount_diff_inr: float
    amount_diff_percent: float
    correlation_score: float  # 0.0 to 1.0
    is_correlated: bool
    explanation: str


class UTRCorrelationRequest(BaseModel):
    victim_utr: str
    amount_inr: float
    utr_timestamp: datetime
    address: Optional[str] = None
    chain: Optional[str] = "ETH"
    time_tolerance_minutes: float = 120.0
    amount_tolerance_percent: float = 5.0
    exchange_rate_inr: Optional[float] = None  # e.g., 250000.0 INR/ETH


class UTRCorrelationResult(BaseModel):
    victim_utr: str
    reported_amount_inr: float
    utr_timestamp: datetime
    time_tolerance_minutes: float
    amount_tolerance_percent: float
    total_candidates_evaluated: int
    matched_candidates: List[UTRCandidateMatch] = []
    best_candidate: Optional[UTRCandidateMatch] = None
    correlation_status: str  # "CORRELATED_MATCH_FOUND", "NO_CANDIDATE_WITHIN_TOLERANCE"


# ==============================================================================
# Phase 7 — Golden Hour Watchlist Schemas
# ==============================================================================

class WatchlistEntryCreate(BaseModel):
    address: str
    chain: str = "ETH"
    case_id: str
    alert_channel: Optional[str] = "TELEGRAM"


class WatchlistEntryOut(BaseModel):
    id: str
    address: str
    chain: str
    case_id: str
    alert_channel: Optional[str] = None
    created_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    status: str
    last_alert_at: Optional[datetime] = None
    last_seen_tx_hash: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class WatchlistPollResult(BaseModel):
    total_checked: int
    alerts_fired: int
    alert_details: List[Dict[str, Any]] = []


# ==============================================================================
# Phase 7 — VASP Directory Admin Schemas
# ==============================================================================

class VASPCreate(BaseModel):
    entity_name: str
    chain: Optional[str] = "ETH"
    hot_wallet_addresses: List[str] = []
    fiu_ind_registered: bool = False
    sla_hours: float = 24.0
    nodal_contact: Optional[str] = None


class VASPUpdate(BaseModel):
    chain: Optional[str] = None
    hot_wallet_addresses: Optional[List[str]] = None
    fiu_ind_registered: Optional[bool] = None
    sla_hours: Optional[float] = None
    nodal_contact: Optional[str] = None


class VASPOut(BaseModel):
    entity_name: str
    chain: Optional[str] = None
    hot_wallet_addresses: Optional[List[str]] = []
    fiu_ind_registered: bool = False
    sla_hours: float = 24.0
    nodal_contact: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Phase 7 — Police Intel Exchange Schemas (Hash-and-RBAC)
# ==============================================================================

class IntelTagSubmit(BaseModel):
    address_hash: str  # SHA-256 of lowercase address
    tag: str  # e.g., DIGITAL_ARREST_MULE, P2P_SCAM_SYNDICATE
    district: str


class IntelLookupRequest(BaseModel):
    address_hash: str  # SHA-256 computed client-side


class IntelTagOut(BaseModel):
    address_hash: str
    tag: str
    district: str
    submitted_by: Optional[str] = None
    submitted_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class IntelLookupResponse(BaseModel):
    match_found: bool
    address_hash: str
    tags: List[Dict[str, Any]] = []
    architecture_notice: str = "Hash-and-RBAC architecture: Query verified against SHA-256 digests. Raw address and victim PII never transmitted or stored."


# ==============================================================================
# Phase 7 — "Arjuna" AI Co-pilot Schemas
# ==============================================================================

class ArjunaSummaryRequest(BaseModel):
    language: Optional[str] = "both"  # "en", "hi", "both"


class ArjunaSummaryResponse(BaseModel):
    case_id: str
    ncrp_ref: Optional[str] = None
    summary_en: str
    summary_hi: str
    factual_verification: Dict[str, Any]
    strict_containment_passed: bool

