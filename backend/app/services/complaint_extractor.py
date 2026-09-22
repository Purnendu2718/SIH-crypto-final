"""Deterministic and Guarded AI Complaint Extraction Service.
Extracts cryptocurrency wallet addresses, transaction hashes, near-miss typos,
and verified factual claims with substring containment guards.
Reference: Phase 9 — Complaint intake with guarded extraction, SIH26183.
"""

import re
import unicodedata
from typing import Dict, Any, List, Optional, Tuple, Set

from app.services.address_validator import validate, ValidationResult
from app.services.pii_masker import mask_pii
from app.llm import get_llm_client, AIExtractionOutput, VALID_TYPOLOGIES


# Regex for extracting candidate identifiers:
# 1. 0x-prefixed hex strings (20-100 hex chars, e.g. Ethereum/EVM addresses & tx hashes)
# 2. Bitcoin/Tron/Solana/Bech32 base58/bech32 candidates (25-110 alphanumeric chars)
CANDIDATE_TOKEN_PATTERN = re.compile(
    r"\b0x[a-fA-F0-9]{38,100}\b|\b[a-zA-Z0-9]{25,110}\b"
)


def normalize_text_for_comparison(text: str) -> str:
    """Normalize unicode characters (NFKC) and collapse internal whitespace for containment check."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    # Replace newlines and multiple spaces with a single space
    collapsed = " ".join(normalized.split())
    return collapsed.lower()


def is_substring_contained(quote: str, source_text: str) -> bool:
    """Verify that an evidence quote is strictly an exact substring of the source text."""
    if not quote or not source_text:
        return False
    norm_quote = normalize_text_for_comparison(quote)
    norm_source = normalize_text_for_comparison(source_text)
    return norm_quote in norm_source


def extract_candidate_identifiers(text: str) -> List[str]:
    """Extract candidate crypto addresses and transaction hashes from unformatted text."""
    if not text:
        return []

    # Clean text around punctuation, commas, brackets, quotes
    cleaned = re.sub(r"[\'\"\[\]\(\)\{\}\<\>\,\;\:\?]", " ", text)
    tokens = CANDIDATE_TOKEN_PATTERN.findall(cleaned)

    # Filter out common English/Hindi words that match length but are not crypto identifiers
    seen: Set[str] = set()
    candidates: List[str] = []
    for t in tokens:
        stripped = t.strip()
        # Discard pure alpha words unless they match specific address patterns
        if stripped.isalpha() and len(stripped) < 32 and not stripped.startswith(("bc1", "tb1", "ltc1")):
            continue
        if stripped and stripped not in seen:
            seen.add(stripped)
            candidates.append(stripped)

    return candidates


def evaluate_identifiers(candidates: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate each candidate identifier using address_validator.py.
    Separates into accepted valid addresses and near misses with actionable error hints.
    """
    accepted: List[Dict[str, Any]] = []
    near_misses: List[Dict[str, Any]] = []

    chain_symbol_map = {
        "bitcoin": "BTC",
        "ethereum": "ETH",
        "tron": "TRON",
        "solana": "SOL",
        "litecoin": "LTC",
        "dogecoin": "DOGE",
        "bitcoin_cash": "BCH",
        "xrp_ledger": "XRP",
        "stellar": "XLM",
        "cardano": "ADA",
        "monero": "XMR",
        "polkadot": "DOT",
        "substrate_generic": "SUBSTRATE",
    }

    for token in candidates:
        res: ValidationResult = validate(token)
        if res.is_valid:
            primary_cand = res.candidates[0] if res.candidates else None
            primary_chain = (
                chain_symbol_map.get(primary_cand.chain, primary_cand.chain.upper())
                if primary_cand
                else "UNKNOWN"
            )
            accepted.append({
                "address": token,
                "kind": res.kind,
                "certainty": res.certainty,
                "primary_chain": primary_chain,
                "candidates": [
                    {
                        "chain": c.chain,
                        "address_type": c.address_type,
                        "network": c.network,
                        "checksum_verified": c.checksum_verified,
                        "note": c.note,
                    }
                    for c in res.candidates
                ],
            })
        else:
            # Check if it resembles an address or txhash (near miss)
            # e.g. starts with 0x, 1, 3, bc1, T, L, D, r, G, or has validator error/hint
            is_near_miss_shape = (
                token.startswith("0x")
                or token.startswith(("1", "3", "bc1", "tb1", "T", "L", "D", "r", "G", "addr1"))
                or len(token) in (34, 40, 42, 64)
                or bool(res.hint)
            )
            if is_near_miss_shape:
                near_misses.append({
                    "token": token,
                    "error": res.error or "Invalid address format or checksum verification failure",
                    "hint": res.hint or "Check for character transposition, missing prefix, or 0/O confusion.",
                })

    return accepted, near_misses


def verify_extracted_facts(
    ai_output: AIExtractionOutput, original_text: str
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Verify evidence quotes for every extracted fact against original text.
    Rejects any fact whose quote cannot be proven as a substring of the complaint text.
    """
    verified_facts: List[Dict[str, Any]] = []
    rejected_facts: List[Dict[str, Any]] = []

    # 1. Offence Date
    if ai_output.offence_date:
        quote = ai_output.offence_date_quote or ""
        if quote and is_substring_contained(quote, original_text):
            verified_facts.append({
                "fact_type": "offence_date",
                "value": ai_output.offence_date,
                "evidence_quote": quote,
                "label": "Date of Offence",
                "verified": True,
            })
        else:
            rejected_facts.append({
                "fact_type": "offence_date",
                "claimed_value": ai_output.offence_date,
                "evidence_quote": quote,
                "rejection_reason": "Evidence quote for offence date is not present in original complaint text.",
            })

    # 2. Victim Loss in INR
    if ai_output.victim_loss_inr is not None:
        quote = ai_output.victim_loss_quote or ""
        if quote and is_substring_contained(quote, original_text):
            verified_facts.append({
                "fact_type": "victim_loss_inr",
                "value": ai_output.victim_loss_inr,
                "evidence_quote": quote,
                "label": "Reported Victim Loss (INR)",
                "verified": True,
            })
        else:
            rejected_facts.append({
                "fact_type": "victim_loss_inr",
                "claimed_value": ai_output.victim_loss_inr,
                "evidence_quote": quote,
                "rejection_reason": "Evidence quote for victim loss is not present in original complaint text.",
            })

    # 3. Currency Amounts
    for amt in ai_output.amounts:
        if amt.evidence_quote and is_substring_contained(amt.evidence_quote, original_text):
            verified_facts.append({
                "fact_type": "amount",
                "value": f"{amt.amount} {amt.currency}",
                "amount": amt.amount,
                "currency": amt.currency,
                "evidence_quote": amt.evidence_quote,
                "label": f"Transaction Amount ({amt.currency})",
                "verified": True,
            })
        else:
            rejected_facts.append({
                "fact_type": "amount",
                "claimed_value": f"{amt.amount} {amt.currency}",
                "evidence_quote": amt.evidence_quote,
                "rejection_reason": "Evidence quote for transaction amount is not present in original complaint text.",
            })

    # 4. Entities Referenced (Exchanges, Banks, UPI)
    for ent in ai_output.entities_referenced:
        if ent.evidence_quote and is_substring_contained(ent.evidence_quote, original_text):
            verified_facts.append({
                "fact_type": "entity",
                "value": ent.name,
                "category": ent.category,
                "evidence_quote": ent.evidence_quote,
                "label": f"Referenced Entity ({ent.category.upper()})",
                "verified": True,
            })
        else:
            rejected_facts.append({
                "fact_type": "entity",
                "claimed_value": f"{ent.name} ({ent.category})",
                "evidence_quote": ent.evidence_quote,
                "rejection_reason": f"Evidence quote for entity '{ent.name}' is not present in original complaint text.",
            })

    # 5. Suggested Typology
    if ai_output.suggested_typology:
        typo = ai_output.suggested_typology.lower().strip()
        quote = ai_output.typology_quote or ""
        if typo in VALID_TYPOLOGIES and quote and is_substring_contained(quote, original_text):
            verified_facts.append({
                "fact_type": "typology",
                "value": typo,
                "evidence_quote": quote,
                "label": "Suggested Laundering Typology",
                "verified": True,
            })
        else:
            rejection_reason = (
                f"Typology '{typo}' is not a valid Phase 8 typology enum."
                if typo not in VALID_TYPOLOGIES
                else "Evidence quote for suggested typology is not present in original complaint text."
            )
            rejected_facts.append({
                "fact_type": "typology",
                "claimed_value": typo,
                "evidence_quote": quote,
                "rejection_reason": rejection_reason,
            })

    return verified_facts, rejected_facts


class ComplaintIntakeEngine:
    """Full complaint intake processor combining deterministic validation and guarded LLM extraction."""

    def __init__(self, provider_override: Optional[str] = None):
        self.llm_client = get_llm_client(provider_override)

    def process_complaint(
        self, complaint_text: str, language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute complete intake extraction pipeline:
        1. PII Redaction
        2. Candidate Identifier Scanning & Address Validation
        3. Near-Miss Diagnosis
        4. Guarded AI Fact Extraction (if provider != none)
        5. Exact Substring Evidence Quote Verification
        """
        # Step 1: PII Masking
        masked_text, pii_redactions = mask_pii(complaint_text)

        # Step 2 & 3: Deterministic Candidate Address & Near-Miss Extraction
        candidates = extract_candidate_identifiers(complaint_text)
        accepted_addresses, near_misses = evaluate_identifiers(candidates)

        # Step 4: Guarded LLM Extraction
        provider = self.llm_client.provider_name
        is_deterministic = provider == "none"

        ai_output: Optional[AIExtractionOutput] = None
        provider_note: Optional[str] = None

        if not is_deterministic:
            ai_output, provider_note = self.llm_client.extract_complaint_facts(
                masked_text, language
            )
            if ai_output is None:
                # Degrade gracefully to deterministic mode
                is_deterministic = True

        # Step 5: Substring Containment Verification
        verified_facts: List[Dict[str, Any]] = []
        rejected_facts: List[Dict[str, Any]] = []
        summary = ""
        translation_en = ""

        if ai_output is not None:
            verified_facts, rejected_facts = verify_extracted_facts(
                ai_output, complaint_text
            )
            summary = ai_output.summary or ""
            translation_en = ai_output.translation_en or ""
        else:
            # Deterministic summary
            summary = (
                f"Deterministic intake processed {len(accepted_addresses)} valid crypto identifier(s) "
                f"and {len(near_misses)} near-miss format warning(s)."
            )

        mode_banner = (
            "Running in Deterministic Mode (No external LLM). Address extraction and checksum verification are active."
            if is_deterministic
            else f"Guarded AI Extraction active (Provider: {provider}). Every factual claim verified against source evidence quotes."
        )

        return {
            "provider": provider,
            "is_deterministic": is_deterministic,
            "mode_banner": mode_banner,
            "provider_note": provider_note,
            "masked_text": masked_text,
            "pii_redacted_count": len(pii_redactions),
            "accepted_addresses": accepted_addresses,
            "near_misses": near_misses,
            "extracted_facts": verified_facts,
            "rejected_facts": rejected_facts,
            "summary": summary,
            "translation_en": translation_en,
            "dpdp_notice": (
                "PII masked prior to processing. Original text retained solely for evidence repository "
                "per DPDP 2023 Section 8(4)."
            ),
        }
