"""PDF Evidence Package Generator using ReportLab.
Produces a court-ready electronic forensic report including trace graph summary,
attribution breakdown, typology hits, taint ratio, and a Section 63 BSA-style certificate.
Reference: SIH26183, Ministry of Home Affairs / I4C.
"""

import io
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

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


def generate_pdf_evidence_report(
    case_data: Dict[str, Any],
    forensic_data: Dict[str, Any],
    evidence_hashes: Dict[str, str],
    officer_data: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Generate a high-fidelity PDF forensic evidence report.
    Returns binary PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0f172a"),
        alignment=1,  # Center
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        alignment=1,
    )

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=10,
        spaceAfter=4,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )

    body_bold = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )

    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("CYBER CRIME FORENSICS DIVISION • GOVERNMENT OF INDIA", subtitle_style))
    story.append(Spacer(1, 2))
    story.append(Paragraph("CRYPTOTRACE SENTINEL — FORENSIC EVIDENCE REPORT", title_style))
    story.append(Paragraph("Automated Multi-Hop Blockchain Analytics &amp; VASP Attribution (SIH26183)", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=10))

    # 2. Case & Investigating Officer Details
    officer = officer_data or {}
    ncrp_ref = case_data.get("ncrp_ref", "NCRP/2026/UNASSIGNED")
    victim_utr = case_data.get("victim_utr", "N/A")
    amount_inr = case_data.get("amount_inr")
    inr_str = f"INR {amount_inr:,.2f}" if amount_inr else "Not Specified"
    date_str = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S UTC")

    meta_table_data = [
        [
            Paragraph("<b>NCRP Reference No:</b>", body_style),
            Paragraph(ncrp_ref, body_bold),
            Paragraph("<b>Date of Report:</b>", body_style),
            Paragraph(date_str, body_style),
        ],
        [
            Paragraph("<b>Victim Bank/UPI UTR:</b>", body_style),
            Paragraph(victim_utr, body_style),
            Paragraph("<b>Reported Fraud:</b>", body_style),
            Paragraph(inr_str, body_bold),
        ],
        [
            Paragraph("<b>Investigating Officer:</b>", body_style),
            Paragraph(officer.get("full_name", "Sub-Inspector"), body_bold),
            Paragraph("<b>Badge &amp; District:</b>", body_style),
            Paragraph(f"{officer.get('badge_no', 'N/A')} • {officer.get('district', 'Central')}", body_style),
        ],
    ]

    meta_table = Table(meta_table_data, colWidths=[120, 150, 110, 160])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # 3. Attribution & Off-Ramp Identification
    story.append(Paragraph("1. DESTINATION VASP ATTRIBUTION &amp; CONFIDENCE BREAKDOWN", section_heading))
    attr = forensic_data.get("attribution", {})
    matched_vasp = attr.get("matched_entity", "Insufficient Evidence")
    confidence = attr.get("confidence", 0.0)
    band = attr.get("confidence_band", "INSUFFICIENT_EVIDENCE")
    rule = attr.get("rule_fired", "HEURISTIC_SEARCH")

    attr_summary_data = [
        [
            Paragraph("<b>Attributed Receiving VASP:</b>", body_style),
            Paragraph(f"<b>{matched_vasp}</b>", body_bold),
            Paragraph("<b>Confidence Band:</b>", body_style),
            Paragraph(f"<b>{band} ({round(confidence * 100, 1)}%)</b>", body_bold),
        ],
        [
            Paragraph("<b>Primary Forensic Rule Fired:</b>", body_style),
            Paragraph(rule, code_style),
            Paragraph("<b>Hop-to-VASP Status:</b>", body_style),
            Paragraph(forensic_data.get("status", "COMPLETED"), body_bold),
        ],
    ]
    attr_table = Table(attr_summary_data, colWidths=[140, 150, 110, 140])
    attr_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dbeafe")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(attr_table)
    story.append(Spacer(1, 8))

    # 4. Hop-by-Hop Trace Summary Table
    story.append(Paragraph("2. MULTI-HOP FUND FLOW AUDIT TRAIL", section_heading))
    trace_info = forensic_data.get("trace", {})
    paths = trace_info.get("paths", [])

    trace_table_data = [
        [
            Paragraph("<b>Hop #</b>", body_bold),
            Paragraph("<b>From Address</b>", body_bold),
            Paragraph("<b>To Address</b>", body_bold),
            Paragraph("<b>Value</b>", body_bold),
            Paragraph("<b>Network</b>", body_bold),
            Paragraph("<b>Transaction Hash</b>", body_bold),
        ]
    ]

    for p in paths:
        from_short = f"{p['from_addr'][:10]}...{p['from_addr'][-6:]}" if len(p['from_addr']) > 20 else p['from_addr']
        to_short = f"{p['to_addr'][:10]}...{p['to_addr'][-6:]}" if len(p['to_addr']) > 20 else p['to_addr']
        tx_short = f"{p['tx_hash'][:12]}...{p['tx_hash'][-6:]}" if p.get('tx_hash') and len(p['tx_hash']) > 20 else (p.get('tx_hash') or "—")
        trace_table_data.append([
            Paragraph(str(p["hop_index"]), body_style),
            Paragraph(from_short, code_style),
            Paragraph(to_short, code_style),
            Paragraph(str(p["value"]), body_style),
            Paragraph(p.get("chain", "ETH"), body_style),
            Paragraph(tx_short, code_style),
        ])

    trace_table = Table(trace_table_data, colWidths=[35, 125, 125, 55, 45, 155])
    trace_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(trace_table)
    story.append(Spacer(1, 8))

    # 5. Typology, FIFO Taint & Risk Assessment
    story.append(Paragraph("3. LAUNDERING TYPOLOGY, FIFO TAINT &amp; COMPOSITE RISK", section_heading))
    typos = forensic_data.get("typologies", [])
    typo_names = ", ".join([t["typology"] for t in typos]) if typos else "None Detected (Direct Flow)"
    taint = forensic_data.get("taint", {})
    taint_pct = taint.get("final_taint_percentage", 100.0)
    risk = forensic_data.get("risk", {})
    risk_score = risk.get("composite_score", 0)
    risk_level = risk.get("risk_level", "LOW")

    risk_table_data = [
        [
            Paragraph("<b>Detected Laundering Typologies:</b>", body_style),
            Paragraph(typo_names, body_bold),
        ],
        [
            Paragraph("<b>FIFO Taint Contamination:</b>", body_style),
            Paragraph(f"{taint_pct:.1f}% attributable to reported theft principal", body_style),
        ],
        [
            Paragraph("<b>Composite Forensic Risk Score:</b>", body_style),
            Paragraph(f"<b>{risk_score}/100 — {risk_level} RISK</b>", body_bold),
        ],
        [
            Paragraph("<b>Forensic Summary / Explanation:</b>", body_style),
            Paragraph(risk.get("explanation", "Forensic evaluation completed."), body_style),
        ],
    ]
    risk_table = Table(risk_table_data, colWidths=[160, 380])
    risk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(risk_table)
    story.append(Spacer(1, 10))

    # 6. Section 63 BSA Electronic Records Certificate
    cert_elements = []
    cert_elements.append(Paragraph("4. CERTIFICATE UNDER SECTION 63 OF BHARATIYA SAKSHYA ADHINIYAM (BSA), 2023", section_heading))
    cert_elements.append(Paragraph(
        "<i>(Admissibility of Electronic Records in Court Proceedings — erstwhile Section 65B of Indian Evidence Act, 1872)</i>",
        subtitle_style,
    ))
    cert_elements.append(Spacer(1, 4))

    sha256_hash = evidence_hashes.get("sha256_hash", "N/A")
    merkle_root = evidence_hashes.get("merkle_root", "N/A")

    cert_table_data = [
        [Paragraph("<b>Record Description:</b>", body_style), Paragraph("Serialized JSON Trace Data, Multi-Hop Graph State, and VASP Attribution Matrix", body_style)],
        [Paragraph("<b>Producing Process:</b>", body_style), Paragraph("CryptoTrace Sentinel Automated Forensic Trace Engine (Self-Hostable, Tamper-Evident)", body_style)],
        [Paragraph("<b>Cryptographic Hash (SHA-256):</b>", body_style), Paragraph(sha256_hash, code_style)],
        [Paragraph("<b>Evidence Merkle Root:</b>", body_style), Paragraph(merkle_root, code_style)],
        [Paragraph("<b>Certified Timestamp:</b>", body_style), Paragraph(date_str, body_style)],
    ]
    cert_table = Table(cert_table_data, colWidths=[150, 390])
    cert_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fefce8")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#fde047")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#fef08a")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    cert_elements.append(cert_table)
    cert_elements.append(Spacer(1, 10))

    cert_elements.append(Paragraph(
        "<b>OFFICER ATTESTATION:</b> I, the undersigned Investigating Officer, hereby certify that the electronic "
        "record described above was generated through automated computational procedures operating in the ordinary course "
        "of official duties. The system was functioning properly with cryptographic tamper-evident logging intact, "
        "and the integrity of the data has not been compromised.",
        body_style,
    ))
    cert_elements.append(Spacer(1, 18))

    sig_data = [
        [
            Paragraph("<b>Date:</b> " + datetime.now(timezone.utc).strftime("%d-%B-%Y"), body_style),
            Paragraph("<b>Signature of Investigating Officer:</b> ___________________________", body_style),
        ],
        [
            Paragraph("<b>Official Police Seal:</b> [SEAL HERE]", body_style),
            Paragraph(f"<b>Name / Badge:</b> {officer.get('full_name', 'Investigating Officer')} ({officer.get('badge_no', 'N/A')})", body_style),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[200, 340])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    cert_elements.append(sig_table)

    story.append(KeepTogether(cert_elements))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
