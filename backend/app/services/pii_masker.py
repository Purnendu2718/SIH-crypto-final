"""Indian Personal Identifiable Information (PII) Masker.
Detects and redacts Phone Numbers, Aadhaar, PAN, and Bank Account numbers
under Digital Personal Data Protection Act, 2023 (DPDP Act 2023) guidelines.
Reference: Phase 9 — Complaint intake with guarded extraction, SIH26183.
"""

import re
from typing import Tuple, List, Dict, Any


# 1. Indian Mobile Number (10 digits starting with 6, 7, 8, or 9, optional +91 or 0 prefix)
PHONE_PATTERN = re.compile(r"(?:\+?91[\s\-]?)?(?:\b0)?[6-9]\d{9}\b")

# 2. Aadhaar Number (12 digits, often 4-4-4, starting with 2-9)
AADHAAR_PATTERN = re.compile(r"\b[2-9]\d{3}[\s\-]\d{4}[\s\-]\d{4}\b|\b[2-9]\d{11}\b")

# 3. PAN (Permanent Account Number - 5 uppercase letters, 4 digits, 1 uppercase letter)
PAN_PATTERN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# 4. Bank Account Number (preceded by keywords or 9-18 digit sequences)
BANK_ACCOUNT_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:a/c|acct|account|acc|khata|खाता|acc\s*no|a/c\s*no)[\s\:\#\-]*(\d{9,18})\b"
)
STANDALONE_ACCOUNT_PATTERN = re.compile(r"\b\d{14,18}\b")


def mask_pii(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Mask Indian PII entities in text and return sanitized string and audit counts.
    Ensures PII is redacted prior to external AI transmission or logging.
    """
    if not text:
        return "", []

    redacted_items: List[Dict[str, Any]] = []
    masked = text

    # Mask PAN first (case-sensitive)
    for m in PAN_PATTERN.finditer(text):
        pan_val = m.group(0)
        redacted_items.append({"type": "PAN", "length": len(pan_val)})
    masked = PAN_PATTERN.sub("[PAN_REDACTED]", masked)

    # Mask Bank Accounts with context keywords
    def _sub_bank_context(match):
        full = match.group(0)
        acc_digits = match.group(1)
        redacted_items.append({"type": "BANK_ACCOUNT", "length": len(acc_digits)})
        return full.replace(acc_digits, "[ACCOUNT_REDACTED]")

    masked = BANK_ACCOUNT_CONTEXT_PATTERN.sub(_sub_bank_context, masked)

    # Mask Aadhaar
    for m in AADHAAR_PATTERN.finditer(masked):
        aadhaar_val = m.group(0)
        # Avoid masking hex addresses that might have 12 digits
        if not aadhaar_val.startswith("0x"):
            redacted_items.append({"type": "AADHAAR", "length": len(aadhaar_val)})
    masked = AADHAAR_PATTERN.sub("[AADHAAR_REDACTED]", masked)

    # Mask Phone Numbers
    for m in PHONE_PATTERN.finditer(masked):
        phone_val = m.group(0)
        redacted_items.append({"type": "PHONE", "length": len(phone_val)})
    masked = PHONE_PATTERN.sub("[PHONE_REDACTED]", masked)

    # Standalone Long Bank Accounts (14-18 digits not already caught)
    for m in STANDALONE_ACCOUNT_PATTERN.finditer(masked):
        acc_val = m.group(0)
        redacted_items.append({"type": "BANK_ACCOUNT", "length": len(acc_val)})
    masked = STANDALONE_ACCOUNT_PATTERN.sub("[ACCOUNT_REDACTED]", masked)

    return masked, redacted_items
