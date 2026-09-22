"""Pydantic schemas for LLM extraction and structured fact verification.
Reference: Phase 9 — Complaint intake with guarded extraction, SIH26183.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


VALID_TYPOLOGIES = {
    "investment_scam",
    "phishing_impersonation",
    "hack_theft",
    "ransomware_extortion",
    "sextortion",
    "insider_misappropriation",
    "layering_laundering",
}


class AmountFact(BaseModel):
    amount: float
    currency: str = "INR"
    evidence_quote: str
    verified: bool = True
    rejection_reason: Optional[str] = None


class EntityFact(BaseModel):
    name: str
    category: str = "exchange"  # exchange, bank, upi, payment_gateway, unknown
    evidence_quote: str
    verified: bool = True
    rejection_reason: Optional[str] = None


class AIExtractionOutput(BaseModel):
    offence_date: Optional[str] = None
    offence_date_quote: Optional[str] = None
    amounts: List[AmountFact] = []
    victim_loss_inr: Optional[float] = None
    victim_loss_quote: Optional[str] = None
    entities_referenced: List[EntityFact] = []
    suggested_typology: Optional[str] = None
    typology_quote: Optional[str] = None
    translation_en: Optional[str] = None
    summary: str = ""
