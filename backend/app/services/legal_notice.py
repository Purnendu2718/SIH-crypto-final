"""Section 94 BNSS (Bharatiya Nagarik Suraksha Sanhita, 2023) Statutory Notice Generator.
Replaces erstwhile Section 91 CrPC for requisitioning digital KYC, transaction records,
and account freezing directives from cryptocurrency exchanges / VASPs.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone


def generate_section_94_bnss_notice(
    ncrp_ref: str,
    vasp_name: str,
    nodal_contact: str,
    suspect_address: str,
    chain: str,
    tx_hashes: List[str],
    amount_inr: Optional[float] = None,
    victim_utr: Optional[str] = None,
    officer_name: str = "Investigating Officer",
    badge_no: str = "N/A",
    district: str = "Cyber Crime Cell",
    timestamps: Optional[List[str]] = None,
) -> str:
    """Generate Section 94 BNSS statutory requisition notice text.
    Pre-fills exchange nodal contact, NCRP reference, suspect address, tx hashes, and INR value.
    Mandatorily ends with review disclaimer.
    """
    date_today = datetime.now(timezone.utc).strftime("%d-%B-%Y")
    tx_hashes_str = "\n".join([f"    • {h}" for h in tx_hashes]) if tx_hashes else f"    • Direct flow from {suspect_address}"
    inr_str = f"₹{amount_inr:,.2f} INR" if amount_inr else "Reported illicit cryptocurrency proceeds"
    utr_str = victim_utr or "Reported via NCRP cyber fraud complaint"

    notice_text = f"""OFFICE OF THE INVESTIGATING OFFICER
CYBER CRIME POLICE STATION / {district.upper()}
GOVERNMENT OF INDIA / STATE POLICE DEPARTMENT

NOTICE UNDER SECTION 94 OF THE BHARATIYA NAGARIK SURAKSHA SANHITA (BNSS), 2023
(Corresponding to Section 91 of the erstwhile Code of Criminal Procedure, 1973)

Dated: {date_today}
Ref: Case NCRP No. {ncrp_ref}

TO:
The Nodal Officer / Compliance Department
{vasp_name} (Registered Virtual Digital Asset Service Provider / VASP)
Email / Nodal Channel: {nodal_contact}

SUBJECT: STATUTORY REQUISITION OF BENEFICIARY KYC, LINKED BANK ACCOUNTS, IP ACCESS LOGS, AND DEBIT FREEZE DIRECTIVE IN CYBERCRIME INVESTIGATION.

WHEREAS an investigation into financial fraud and unauthorized cryptocurrency diversion has been initiated on the National Cybercrime Reporting Portal (NCRP) under Reference No. {ncrp_ref}.

WHEREAS automated forensic blockchain analytics have traced victim funds totaling {inr_str} (Victim Bank UTR: {utr_str}) directly into deposit/hot wallet infrastructure controlled and managed by your platform ({vasp_name}).

DETAILS OF FORENSICALLY TRACED TRANSACTIONS:
1. Suspect Source Address: {suspect_address} ({chain})
2. Receiving VASP / Entity: {vasp_name}
3. Relevant Blockchain Transaction Hash(es):
{tx_hashes_str}

NOW THEREFORE, in exercise of powers conferred upon me under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, you are hereby directed to produce and furnish the following certified electronic records within 24 HOURS of receipt of this notice:

1. BENEFICIARY IDENTITY & KYC: Certified full name, registered mobile number, email address, PAN, Aadhaar/Passport, and PMLA-compliant onboarding documentation of the account holder(s) who received or credited the aforementioned transaction(s).
2. BANKING DETAILS: All bank account numbers, IFSC codes, UPI handles, and withdrawal destinations associated with the beneficiary UID/account.
3. IP ACCESS & DEVICE LOGS: Timestamped login, session, and transaction IP logs (including port numbers, VPN indicators, and device MAC/IMEI fingerprints) associated with the beneficiary account for the 30-day window surrounding the incident.
4. IMMEDIATE ACCOUNT RESTRICTION: Immediate lien / debit-freeze of the recipient account/wallet to preserve crime proceeds from dissipation, in accordance with applicable statutory mandates.

Please treat this notice on priority in view of ongoing tracing of financial cyber fraud proceeds. All certified electronic records must be accompanied by an Electronic Record Certificate under Section 63 of the Bharatiya Sakshya Adhiniyam (BSA), 2023.

Issued under my hand and seal:

Name: {officer_name}
Rank/Badge: {badge_no}
Police Station/Unit: {district}

Draft for review by the investigating officer / department legal cell before issuance.
"""
    return notice_text.strip()
