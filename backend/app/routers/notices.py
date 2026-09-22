"""Statutory Notice & Email Drafter API Router.
Handles drafting, guarded tone polish, human approval workflow, EML/PDF downloads,
and dry-run/SMTP dispatch with full audit logging.
Reference: Phase 10 — Notice and email drafter with approval workflow, SIH26183.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    Profile,
    Case,
    WalletSubmission,
    Notice,
    NoticeEvent,
    generate_uuid,
    utc_now,
)
from app.security import get_current_officer
from app.schemas import (
    NoticeCreateRequest,
    NoticeUpdateRequest,
    NoticePolishRequest,
    NoticePolishResponse,
    NoticeOut,
    NoticeEventOut,
    NoticeListResponse,
    NoticeActionResponse,
)
from app.services.notice_service import (
    render_notice_template,
    polish_notice_tone,
    generate_eml,
    generate_notice_pdf,
    dispatch_notice,
    get_exchange_contacts,
    DEFAULT_LEGAL_BASIS,
)
from app.services.audit import append_audit_entry


router = APIRouter(prefix="/api", tags=["Statutory Notices"])
router_v1 = APIRouter(prefix="/api/v1", tags=["Statutory Notices (v1)"])


def check_case_access(case: Case, officer: Profile) -> None:
    """Ensure officer has access to case under RLS rules."""
    if officer.role == "INVESTIGATOR" and case.assigned_officer_id and case.assigned_officer_id != officer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access unauthorized under current officer clearance. Case belongs to another investigator.",
        )


def format_notice_out(n: Notice) -> NoticeOut:
    """Convert Notice model to NoticeOut schema with relational names."""
    creator_name = n.creator.full_name if n.creator else None
    approver_name = n.approver.full_name if n.approver else None
    events_out = [
        NoticeEventOut(
            id=e.id,
            event_type=e.event_type,
            from_status=e.from_status,
            to_status=e.to_status,
            actor_id=e.actor_id,
            actor_name=e.actor.full_name if e.actor else None,
            notes=e.notes,
            created_at=e.created_at,
        )
        for e in n.events
    ]
    return NoticeOut(
        id=n.id,
        case_id=n.case_id,
        kind=n.kind,
        recipient_name=n.recipient_name,
        recipient_email=n.recipient_email,
        subject=n.subject,
        body=n.body,
        status=n.status,
        created_by=n.created_by,
        creator_name=creator_name,
        approved_by=n.approved_by,
        approver_name=approver_name,
        legal_basis_text=n.legal_basis_text,
        attachments=n.attachments or [],
        due_at=n.due_at,
        sent_at=n.sent_at,
        created_at=n.created_at,
        updated_at=n.updated_at,
        events=events_out,
    )


# ==============================================================================
# Case Notices Endpoints
# ==============================================================================

@router.get("/cases/{case_id}/notices", response_model=NoticeListResponse)
@router_v1.get("/cases/{case_id}/notices", response_model=NoticeListResponse)
def list_case_notices(
    case_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """List all statutory notices created for a case, along with directory contacts."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    check_case_access(case, current_officer)

    notices = (
        db.query(Notice)
        .filter(Notice.case_id == case_id)
        .order_by(Notice.created_at.desc())
        .all()
    )

    contacts = get_exchange_contacts()
    return NoticeListResponse(
        notices=[format_notice_out(n) for n in notices],
        contacts=contacts,
    )


@router.post("/cases/{case_id}/notices", response_model=NoticeOut)
@router_v1.post("/cases/{case_id}/notices", response_model=NoticeOut)
def create_case_notice_draft(
    case_id: str,
    req: NoticeCreateRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Create a new statutory notice draft using Jinja2 templates (autoescaped) or custom text."""
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    check_case_access(case, current_officer)

    # Collect addresses from case wallet submissions if not explicitly passed
    addrs_to_use = req.addresses
    if not addrs_to_use:
        subs = db.query(WalletSubmission).filter(WalletSubmission.case_id == case_id).all()
        addrs_to_use = [{"chain": s.chain, "address": s.address} for s in subs]

    # Calculate due date
    hours = req.reply_deadline_hours or 48
    due_at = utc_now() + timedelta(hours=hours)

    if req.custom_body:
        body = req.custom_body
        subject = f"Statutory Notice: {req.kind.upper()} Request - Case {case.ncrp_ref or case_id[:8]}"
    else:
        # Render using Jinja2 template
        context = {
            "recipient_name": req.recipient_name,
            "recipient_email": req.recipient_email,
            "case_reference": case.ncrp_ref or f"CASE-{case.case_id[:8]}",
            "fir_reference": req.fir_reference or "Under Investigation / FIR Pending",
            "addresses": addrs_to_use,
            "tx_hashes": req.tx_hashes or [],
            "time_window_start": req.time_window_start or (case.created_at.strftime("%Y-%m-%d") if case.created_at else None),
            "time_window_end": req.time_window_end or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "legal_basis_text": req.legal_basis_text or DEFAULT_LEGAL_BASIS,
            "reply_deadline": f"{hours} hours",
            "due_date": due_at.strftime("%d %B %Y %H:%M UTC"),
            "officer_name": current_officer.full_name,
            "officer_badge": current_officer.badge_no,
            "officer_district": current_officer.district,
            "secure_reply_channel": settings.SMTP_FROM,
        }
        subject, body = render_notice_template(req.kind, context)

    notice_id = generate_uuid()
    new_notice = Notice(
        id=notice_id,
        case_id=case_id,
        kind=req.kind,
        recipient_name=req.recipient_name,
        recipient_email=req.recipient_email,
        subject=subject,
        body=body,
        status="draft",
        created_by=current_officer.id,
        approved_by=None,
        legal_basis_text=req.legal_basis_text or DEFAULT_LEGAL_BASIS,
        attachments=[],
        due_at=due_at,
    )
    db.add(new_notice)
    db.flush()

    # Record notice event
    event = NoticeEvent(
        id=generate_uuid(),
        notice_id=new_notice.id,
        event_type="CREATED_DRAFT",
        from_status=None,
        to_status="draft",
        actor_id=current_officer.id,
        notes=f"Created initial draft for {req.kind.upper()} request.",
    )
    db.add(event)

    # Append to hash-chained audit log
    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="NOTICE_DRAFT_CREATED",
        target_id=new_notice.id,
    )

    db.commit()
    db.refresh(new_notice)
    return format_notice_out(new_notice)


# ==============================================================================
# Single Notice Detail, Edit, Polish, Workflow Endpoints
# ==============================================================================

@router.get("/notices/{notice_id}", response_model=NoticeOut)
@router_v1.get("/notices/{notice_id}", response_model=NoticeOut)
def get_notice_detail(
    notice_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Retrieve full detail and audit history timeline for a notice."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    case = db.query(Case).filter(Case.case_id == notice.case_id).first()
    if case:
        check_case_access(case, current_officer)

    return format_notice_out(notice)


@router.put("/notices/{notice_id}", response_model=NoticeOut)
@router_v1.put("/notices/{notice_id}", response_model=NoticeOut)
def update_notice_draft(
    notice_id: str,
    req: NoticeUpdateRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Edit draft notice. Allowed ONLY while notice status is 'draft'."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    if notice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Notice cannot be edited in '{notice.status}' status. Only drafts may be edited.",
        )

    if req.subject is not None:
        notice.subject = req.subject
    if req.body is not None:
        notice.body = req.body
    if req.recipient_name is not None:
        notice.recipient_name = req.recipient_name
    if req.recipient_email is not None:
        notice.recipient_email = req.recipient_email
    if req.legal_basis_text is not None:
        notice.legal_basis_text = req.legal_basis_text
    if req.due_at is not None:
        notice.due_at = req.due_at

    notice.updated_at = utc_now()

    event = NoticeEvent(
        id=generate_uuid(),
        notice_id=notice.id,
        event_type="EDITED_DRAFT",
        from_status="draft",
        to_status="draft",
        actor_id=current_officer.id,
        notes="Investigating officer modified draft content.",
    )
    db.add(event)
    db.commit()
    db.refresh(notice)
    return format_notice_out(notice)


@router.post("/notices/{notice_id}/polish", response_model=NoticePolishResponse)
@router_v1.post("/notices/{notice_id}/polish", response_model=NoticePolishResponse)
def polish_notice(
    notice_id: str,
    req: NoticePolishRequest,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Guarded LLM tone polish. Discards and rejects output if any address, hash, date, or amount differs."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    original_text = req.body or notice.body
    polished_text, is_polished, note = polish_notice_tone(original_text)

    if is_polished:
        # Update draft if requested on draft notice
        if notice.status == "draft":
            notice.body = polished_text
            notice.updated_at = utc_now()
            event = NoticeEvent(
                id=generate_uuid(),
                notice_id=notice.id,
                event_type="POLISHED",
                from_status="draft",
                to_status="draft",
                actor_id=current_officer.id,
                notes="Tone polished by AI assistant and verified against evidentiary tokens.",
            )
            db.add(event)
            db.commit()

    return NoticePolishResponse(
        notice_id=notice.id,
        original_body=original_text,
        polished_body=polished_text,
        is_polished=is_polished,
        note=note,
    )


@router.post("/notices/{notice_id}/submit", response_model=NoticeActionResponse)
@router_v1.post("/notices/{notice_id}/submit", response_model=NoticeActionResponse)
def submit_notice_for_approval(
    notice_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Investigator submits draft notice for supervisor/approver authorization."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    if notice.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only draft notices can be submitted for approval (current: {notice.status}).",
        )

    notice.status = "pending_approval"
    notice.updated_at = utc_now()

    event = NoticeEvent(
        id=generate_uuid(),
        notice_id=notice.id,
        event_type="SUBMITTED_FOR_APPROVAL",
        from_status="draft",
        to_status="pending_approval",
        actor_id=current_officer.id,
        notes="Submitted for supervisory legal and compliance approval.",
    )
    db.add(event)

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="NOTICE_SUBMITTED_FOR_APPROVAL",
        target_id=notice.id,
    )

    db.commit()
    return NoticeActionResponse(
        notice_id=notice.id,
        status="pending_approval",
        message="Notice submitted for approval. Awaiting review by Approver / Supervisor / Admin.",
        dry_run=settings.MAIL_DRY_RUN,
    )


@router.post("/notices/{notice_id}/approve", response_model=NoticeActionResponse)
@router_v1.post("/notices/{notice_id}/approve", response_model=NoticeActionResponse)
def approve_notice(
    notice_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Authorize notice. ONLY officers with APPROVER, SUPERVISOR, or ADMIN role can approve.
    Investigators CANNOT approve (strictly enforces human approval workflow).
    """
    allowed_roles = {"APPROVER", "SUPERVISOR", "ADMIN"}
    if current_officer.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Investigators cannot approve notices. Clearance required: {', '.join(allowed_roles)}.",
        )

    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    if notice.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Notice must be in 'pending_approval' status to approve (current: {notice.status}).",
        )

    notice.status = "approved"
    notice.approved_by = current_officer.id
    notice.updated_at = utc_now()

    event = NoticeEvent(
        id=generate_uuid(),
        notice_id=notice.id,
        event_type="APPROVED",
        from_status="pending_approval",
        to_status="approved",
        actor_id=current_officer.id,
        notes=f"Approved by {current_officer.full_name} ({current_officer.role}). Ready for dispatch.",
    )
    db.add(event)

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action="NOTICE_APPROVED",
        target_id=notice.id,
    )

    db.commit()
    return NoticeActionResponse(
        notice_id=notice.id,
        status="approved",
        message="Notice approved. Officer may now dispatch via SMTP or generate .eml outbox package.",
        dry_run=settings.MAIL_DRY_RUN,
    )


@router.post("/notices/{notice_id}/send", response_model=NoticeActionResponse)
@router_v1.post("/notices/{notice_id}/send", response_model=NoticeActionResponse)
def send_approved_notice(
    notice_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Dispatch notice. Notice MUST be approved. In dry-run mode (default), writes .eml to outbox/."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    if notice.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only approved notices may be sent (current: {notice.status}). Approval and sending are separate steps.",
        )

    case = db.query(Case).filter(Case.case_id == notice.case_id).first()
    case_ref = case.ncrp_ref if case and case.ncrp_ref else f"CASE-{notice.case_id[:8]}"

    success, message, eml_path = dispatch_notice(notice, case_ref, current_officer, db)
    if not success:
        raise HTTPException(status_code=500, detail=message)

    return NoticeActionResponse(
        notice_id=notice.id,
        status="sent",
        message=message,
        eml_path=eml_path,
        dry_run=settings.MAIL_DRY_RUN,
    )


@router.get("/notices/{notice_id}/download-eml")
@router_v1.get("/notices/{notice_id}/download-eml")
def download_eml(
    notice_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Download RFC-822 .eml file for notice."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    case = db.query(Case).filter(Case.case_id == notice.case_id).first()
    case_ref = case.ncrp_ref if case and case.ncrp_ref else f"CASE-{notice.case_id[:8]}"

    pdf_bytes = generate_notice_pdf(notice, case_ref, current_officer)
    msg = generate_eml(notice, case_ref, settings.SMTP_FROM, pdf_bytes)

    headers = {
        "Content-Disposition": f"attachment; filename=notice_{notice.id[:8]}.eml",
        "Content-Type": "message/rfc822",
    }
    return Response(content=msg.as_bytes(), media_type="message/rfc822", headers=headers)


@router.get("/notices/{notice_id}/download-pdf")
@router_v1.get("/notices/{notice_id}/download-pdf")
def download_pdf(
    notice_id: str,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Download ReportLab PDF requisition for notice."""
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    case = db.query(Case).filter(Case.case_id == notice.case_id).first()
    case_ref = case.ncrp_ref if case and case.ncrp_ref else f"CASE-{notice.case_id[:8]}"

    pdf_bytes = generate_notice_pdf(notice, case_ref, current_officer)

    headers = {
        "Content-Disposition": f"attachment; filename=statutory_notice_{notice.id[:8]}.pdf",
        "Content-Type": "application/pdf",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.post("/notices/{notice_id}/status", response_model=NoticeActionResponse)
@router_v1.post("/notices/{notice_id}/status", response_model=NoticeActionResponse)
def update_notice_status(
    notice_id: str,
    target_status: str,
    notes: Optional[str] = None,
    current_officer: Profile = Depends(get_current_officer),
    db: Session = Depends(get_db),
):
    """Mark notice as 'replied' or 'cancelled'."""
    allowed_targets = {"replied", "cancelled"}
    if target_status not in allowed_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Target status must be one of: {allowed_targets}",
        )

    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail=f"Notice '{notice_id}' not found.")

    old_status = notice.status
    notice.status = target_status
    notice.updated_at = utc_now()

    event = NoticeEvent(
        id=generate_uuid(),
        notice_id=notice.id,
        event_type="STATUS_CHANGED",
        from_status=old_status,
        to_status=target_status,
        actor_id=current_officer.id,
        notes=notes or f"Status updated from {old_status} to {target_status}",
    )
    db.add(event)

    append_audit_entry(
        db=db,
        officer_id=current_officer.id,
        action=f"NOTICE_STATUS_{target_status.upper()}",
        target_id=notice.id,
    )
    db.commit()

    return NoticeActionResponse(
        notice_id=notice.id,
        status=target_status,
        message=f"Notice status transitioned to {target_status}.",
        dry_run=settings.MAIL_DRY_RUN,
    )
