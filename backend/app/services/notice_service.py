"""Statutory Notice & Email Drafter Service.
Handles Jinja2 rendering with autoescape, guarded LLM tone polish, RFC-822 EML generation,
ReportLab PDF notice generation, and dry-run/SMTP dispatch with audit logging.
Reference: Phase 10 — Notice and email drafter with approval workflow, SIH26183.
"""

import io
import json
import os
import re
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import make_msgid, formatdate
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

import jinja2
from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)

from app.config import settings
from app.models import Notice, NoticeEvent, Profile, Case, generate_uuid, utc_now
from app.llm import get_llm_client
from app.services.audit import append_audit_entry


# Templates directory
TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "notices"

# Jinja2 environment with strict autoescape enabled to prevent template injection
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)

DEFAULT_LEGAL_BASIS = (
    "under the applicable provisions of the Bharatiya Nagarik Suraksha Sanhita, 2023 "
    "(section to be confirmed by the investigating officer)"
)


# ==============================================================================
# 1. Exchange Contacts Directory Loader
# ==============================================================================

def get_exchange_contacts() -> List[Dict[str, Any]]:
    """Load known exchange nodal officer directory from data/exchange_contacts.example.json."""
    contacts_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "exchange_contacts.example.json"
    if not contacts_path.exists():
        # Fallback to backend root
        contacts_path = Path(__file__).resolve().parent.parent.parent / "data" / "exchange_contacts.example.json"

    if contacts_path.exists():
        try:
            with open(contacts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


# ==============================================================================
# 2. Template Rendering
# ==============================================================================

def render_notice_template(
    template_kind: str,
    context: Dict[str, Any],
) -> Tuple[str, str]:
    """Render a statutory notice template.
    template_kind: 'preservation', 'freeze', or 'reminder'
    Returns: (subject, rendered_body)
    """
    template_name = f"{template_kind}_request.j2" if template_kind in ("preservation", "freeze") else f"{template_kind}_notice.j2"
    template = jinja_env.get_template(template_name)

    # Ensure required defaults
    if not context.get("legal_basis_text"):
        context["legal_basis_text"] = DEFAULT_LEGAL_BASIS
    if not context.get("current_date"):
        context["current_date"] = datetime.now(timezone.utc).strftime("%d %B %Y")

    rendered = template.render(**context)

    # Derive subject line from template output
    subject = f"Statutory Notice: {template_kind.upper()} Request - Case {context.get('case_reference', 'N/A')}"
    for line in rendered.splitlines():
        if line.strip().startswith("Subject:"):
            subject = line.replace("Subject:", "").strip()
            break

    return subject, rendered


# ==============================================================================
# 3. Guarded LLM Tone Polish & Safety Cross-Verification
# ==============================================================================

# Regex patterns for critical evidentiary tokens that MUST NOT change during polish
ADDR_PATTERN = re.compile(r"\b0x[a-fA-F0-9]{38,42}\b|\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b|\bbc1[a-zA-HJ-NP-Z0-9]{25,90}\b|\bT[a-km-zA-HJ-NP-Z1-9]{33}\b")
HASH_PATTERN = re.compile(r"\b(?:0x)?[a-fA-F0-9]{64}\b")
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b", re.IGNORECASE)
AMOUNT_PATTERN = re.compile(r"\b\d+(?:,\d+)*(?:\.\d+)?\s*(?:INR|USD|USDT|ETH|BTC|₹|\$)\b|\b₹\s*\d+(?:,\d+)*(?:\.\d+)?\b|\b\d{4,12}\b")


def extract_evidentiary_tokens(text: str) -> Dict[str, Set[str]]:
    """Extract all addresses, transaction/manifest hashes, dates, and amounts from text."""
    if not text:
        return {"addresses": set(), "hashes": set(), "dates": set(), "amounts": set()}

    addresses = {a.lower() for a in ADDR_PATTERN.findall(text)}
    hashes = {h.lower() for h in HASH_PATTERN.findall(text)}
    dates = {d.strip().lower() for d in DATE_PATTERN.findall(text)}
    amounts = {a.strip().lower() for a in AMOUNT_PATTERN.findall(text)}

    return {
        "addresses": addresses,
        "hashes": hashes,
        "dates": dates,
        "amounts": amounts,
    }


def verify_polish_integrity(original_text: str, candidate_text: str) -> Tuple[bool, Optional[str]]:
    """Verify that polished text does NOT alter, omit, or introduce any addresses,
    hashes, dates, or numerical amounts.
    """
    orig_tokens = extract_evidentiary_tokens(original_text)
    cand_tokens = extract_evidentiary_tokens(candidate_text)

    # 1. Check addresses
    if orig_tokens["addresses"] != cand_tokens["addresses"]:
        diff = orig_tokens["addresses"] ^ cand_tokens["addresses"]
        return False, f"Address integrity mismatch: Polished text modified addresses: {diff}"

    # 2. Check hashes
    if orig_tokens["hashes"] != cand_tokens["hashes"]:
        diff = orig_tokens["hashes"] ^ cand_tokens["hashes"]
        return False, f"Hash integrity mismatch: Polished text modified transaction/evidence hashes: {diff}"

    # 3. Check dates
    if orig_tokens["dates"] != cand_tokens["dates"]:
        diff = orig_tokens["dates"] ^ cand_tokens["dates"]
        return False, f"Date integrity mismatch: Polished text modified dates: {diff}"

    # 4. Check amounts
    if orig_tokens["amounts"] != cand_tokens["amounts"]:
        diff = orig_tokens["amounts"] ^ cand_tokens["amounts"]
        return False, f"Amount integrity mismatch: Polished text modified monetary or token amounts: {diff}"

    return True, None


def polish_notice_tone(original_body: str) -> Tuple[str, bool, Optional[str]]:
    """Request LLM provider to polish tone for clarity and legal formality.
    Strictly discards polished text if evidentiary tokens are modified.
    Returns: (final_text, is_polished, note)
    """
    llm_client = get_llm_client()
    if llm_client.provider_name == "none":
        return original_body, False, "Tone polish unavailable in deterministic mode (LLM_PROVIDER=none)."

    system_instruction = (
        "You are an administrative editor for Law Enforcement statutory notices. "
        "Your task is to refine the tone of the draft notice to be authoritative, clear, and formal. "
        "CRITICAL RULE: DO NOT alter, drop, or introduce any cryptocurrency addresses, transaction hashes, "
        "evidence SHA-256 hashes, dates, FIR numbers, case references, or amounts. Every coordinate must remain EXACTLY identical."
    )

    prompt = f"{system_instruction}\n\nDraft Notice to Polish:\n\n{original_body}"

    try:
        if hasattr(llm_client, "_call_api"):
            polished = llm_client._call_api(prompt)  # type: ignore
        else:
            return original_body, False, "Configured LLM client does not support direct prompt completion."

        # Verify integrity
        is_valid, error = verify_polish_integrity(original_body, polished)
        if not is_valid:
            return original_body, False, f"Polished text rejected by safety guard: {error}"

        return polished, True, "Tone successfully polished and verified against evidentiary tokens."
    except Exception as e:
        return original_body, False, f"LLM polish failed: {str(e)}"


# ==============================================================================
# 4. RFC-822 EML Generation
# ==============================================================================

def generate_eml(
    notice: Notice,
    case_ref: str,
    from_email: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
) -> EmailMessage:
    """Construct an RFC-822 compliant MIME email message."""
    msg = EmailMessage()
    msg["Subject"] = notice.subject
    msg["From"] = from_email or settings.SMTP_FROM
    msg["To"] = notice.recipient_email
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="cybercrime.gov.in")
    msg["X-Case-Reference"] = case_ref
    msg["X-Notice-ID"] = notice.id
    msg["X-Notice-Kind"] = notice.kind
    msg["X-Statutory-Authority"] = "Bharatiya Nagarik Suraksha Sanhita, 2023"

    msg.set_content(notice.body)

    # Attach PDF if generated
    if pdf_bytes:
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=f"statutory_notice_{notice.id[:8]}.pdf",
        )

    return msg


# ==============================================================================
# 5. PDF Notice Generator (Pure ReportLab)
# ==============================================================================

def generate_notice_pdf(notice: Notice, case_ref: str, officer_profile: Optional[Profile] = None) -> bytes:
    """Generate high-fidelity official police statutory requisition PDF using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    header_style = ParagraphStyle(
        "NoticeHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        alignment=1,  # Center
        textColor=colors.HexColor("#0f172a"),
    )

    sub_header = ParagraphStyle(
        "NoticeSubHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        alignment=1,
        textColor=colors.HexColor("#2563eb"),
    )

    body_style = ParagraphStyle(
        "NoticeBody",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
    )

    story = []

    # Emblems & Heading
    story.append(Paragraph("CYBER CRIME POLICE STATION • LAW ENFORCEMENT AGENCY", header_style))
    story.append(Paragraph("GOVERNMENT OF INDIA • STATUTORY REQUISITION NOTICE", sub_header))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=12))

    # Meta Table
    meta_data = [
        [
            Paragraph("<b>Case Ref (NCRP):</b>", styles["Normal"]),
            Paragraph(case_ref, styles["Normal"]),
            Paragraph("<b>Notice ID:</b>", styles["Normal"]),
            Paragraph(notice.id[:13], styles["Normal"]),
        ],
        [
            Paragraph("<b>Requisition Kind:</b>", styles["Normal"]),
            Paragraph(notice.kind.upper(), styles["Normal"]),
            Paragraph("<b>Status:</b>", styles["Normal"]),
            Paragraph(notice.status.upper(), styles["Normal"]),
        ],
        [
            Paragraph("<b>Recipient:</b>", styles["Normal"]),
            Paragraph(f"{notice.recipient_name} &lt;{notice.recipient_email}&gt;", styles["Normal"]),
            Paragraph("<b>Dispatch Mode:</b>", styles["Normal"]),
            Paragraph("DRY-RUN OUTBOX (.eml)" if settings.MAIL_DRY_RUN else "SMTP DIRECT", styles["Normal"]),
        ],
    ]
    t = Table(meta_data, colWidths=[100, 165, 95, 170])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # Notice Body (formatted text lines)
    for paragraph_text in notice.body.split("\n\n"):
        clean_p = paragraph_text.replace("\n", "<br/>")
        story.append(Paragraph(clean_p, body_style))
        story.append(Spacer(1, 8))

    # Footer signature block
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceAfter=10))

    officer_name = officer_profile.full_name if officer_profile else "Investigating Officer"
    badge_no = officer_profile.badge_no if officer_profile else "N/A"
    sig_text = (
        f"<b>Digitally Authored by:</b> {officer_name} (Badge: {badge_no})<br/>"
        f"<b>Status:</b> {notice.status.upper()} • <b>Generated at:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}<br/>"
        f"<i>Draft for statutory compliance under Indian Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023.</i>"
    )
    story.append(Paragraph(sig_text, styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()


# ==============================================================================
# 6. Dispatch & Outbox Management
# ==============================================================================

def dispatch_notice(
    notice: Notice,
    case_ref: str,
    officer: Profile,
    db_session: Any,
) -> Tuple[bool, str, Optional[str]]:
    """Dispatch notice via SMTP or write to local .eml outbox if MAIL_DRY_RUN is True.
    Notice MUST be in 'approved' status.
    Returns: (success, message, eml_path)
    """
    if notice.status != "approved":
        return False, f"Notice status must be 'approved' to send (current: {notice.status}).", None

    pdf_bytes = generate_notice_pdf(notice, case_ref, officer)
    msg = generate_eml(notice, case_ref, settings.SMTP_FROM, pdf_bytes)

    outbox_dir = Path(settings.OUTBOX_DIR)
    outbox_dir.mkdir(parents=True, exist_ok=True)
    eml_file_path = outbox_dir / f"{notice.id}.eml"

    if settings.MAIL_DRY_RUN:
        # Dry-run: Write to .eml file
        with open(eml_file_path, "wb") as f:
            f.write(msg.as_bytes())

        # Update notice status to sent
        old_status = notice.status
        notice.status = "sent"
        notice.sent_at = utc_now()

        # Record event
        event = NoticeEvent(
            id=generate_uuid(),
            notice_id=notice.id,
            event_type="SENT",
            from_status=old_status,
            to_status="sent",
            actor_id=officer.id,
            notes=f"Dispatched in DRY-RUN mode. EML written to {eml_file_path}",
        )
        db_session.add(event)

        # Audit log
        append_audit_entry(
            db=db_session,
            officer_id=officer.id,
            action="NOTICE_DISPATCHED_DRY_RUN",
            target_id=notice.id,
        )
        db_session.commit()

        return True, f"Dry-run dispatch complete. EML written to {eml_file_path}", str(eml_file_path)

    else:
        # Live SMTP sending
        try:
            with smtplib.SMTP(settings.SMTP_HOST or "localhost", settings.SMTP_PORT) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)

            # Also persist copy in outbox
            with open(eml_file_path, "wb") as f:
                f.write(msg.as_bytes())

            old_status = notice.status
            notice.status = "sent"
            notice.sent_at = utc_now()

            event = NoticeEvent(
                id=generate_uuid(),
                notice_id=notice.id,
                event_type="SENT",
                from_status=old_status,
                to_status="sent",
                actor_id=officer.id,
                notes=f"Live SMTP dispatched to {notice.recipient_email}",
            )
            db_session.add(event)

            append_audit_entry(
                db=db_session,
                officer_id=officer.id,
                action="NOTICE_DISPATCHED_LIVE_SMTP",
                target_id=notice.id,
            )
            db_session.commit()

            return True, f"Live notice sent via SMTP to {notice.recipient_email}", str(eml_file_path)

        except Exception as e:
            return False, f"SMTP dispatch failed: {str(e)}", None


# ==============================================================================
# 7. Follow-up Reminders (Overdue Notices)
# ==============================================================================

def check_and_create_overdue_reminders(db_session: Any) -> List[Notice]:
    """Scan for sent notices whose due_at has elapsed and create DRAFT reminder notices.
    Reminders are NEVER auto-sent — strictly created in 'draft' status for officer review.
    """
    now = utc_now()
    overdue_notices = (
        db_session.query(Notice)
        .filter(
            Notice.status == "sent",
            Notice.kind != "reminder",
            Notice.due_at != None,
            Notice.due_at < now,
        )
        .all()
    )

    created_reminders = []

    for parent in overdue_notices:
        # Check if an active reminder already exists for this parent notice
        existing_reminder = (
            db_session.query(Notice)
            .filter(
                Notice.case_id == parent.case_id,
                Notice.kind == "reminder",
                Notice.recipient_email == parent.recipient_email,
                Notice.status.in_(["draft", "pending_approval", "approved", "sent"]),
            )
            .first()
        )
        if existing_reminder:
            continue

        case = db_session.query(Case).filter(Case.case_id == parent.case_id).first()
        case_ref = case.ncrp_ref if case and case.ncrp_ref else f"CASE-{parent.case_id[:8]}"

        context = {
            "recipient_name": parent.recipient_name,
            "recipient_email": parent.recipient_email,
            "case_reference": case_ref,
            "prior_notice_id": parent.id,
            "original_subject": parent.subject,
            "prior_notice_date": parent.sent_at.strftime("%d %b %Y") if parent.sent_at else "Earlier",
            "due_date": parent.due_at.strftime("%d %b %Y %H:%M UTC") if parent.due_at else "Past Due",
            "legal_basis_text": parent.legal_basis_text or DEFAULT_LEGAL_BASIS,
            "officer_name": "Investigating Officer",
            "addresses": [],
            "tx_hashes": [],
        }

        subject, body = render_notice_template("reminder", context)

        reminder_notice = Notice(
            id=generate_uuid(),
            case_id=parent.case_id,
            kind="reminder",
            recipient_name=parent.recipient_name,
            recipient_email=parent.recipient_email,
            subject=subject,
            body=body,
            status="draft",  # Strictly DRAFT, never auto-sent
            created_by=parent.created_by,
            approved_by=None,
            legal_basis_text=parent.legal_basis_text,
            attachments=[{"prior_notice_id": parent.id, "prior_due_at": parent.due_at.isoformat()}],
            due_at=None,
        )
        db_session.add(reminder_notice)
        db_session.flush()

        event = NoticeEvent(
            id=generate_uuid(),
            notice_id=reminder_notice.id,
            event_type="REMINDER_CREATED",
            from_status=None,
            to_status="draft",
            actor_id=parent.created_by,
            notes=f"Automated draft reminder generated for overdue notice {parent.id}",
        )
        db_session.add(event)

        append_audit_entry(
            db=db_session,
            officer_id=parent.created_by,
            action="REMINDER_NOTICE_DRAFT_CREATED",
            target_id=reminder_notice.id,
        )

        created_reminders.append(reminder_notice)

    db_session.commit()
    return created_reminders

