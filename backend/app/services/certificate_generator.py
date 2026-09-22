"""Section 63 Bharatiya Sakshya Adhiniyam, 2023 (BSA 2023) Electronic Record Certificate Generator.
Generates certificate_draft.pdf for admissibility of electronic blockchain forensic records in Indian courts.
Reference: Section 63 BSA 2023 (formerly Section 65B Indian Evidence Act 1872), SIH26183.
"""

import io
from typing import Dict, Any, Optional
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

LEGAL_STAMP_TEXT = "DRAFT - for review by legal counsel; verify the prescribed Schedule format before use"


def _draw_page_decorations(canvas, doc):
    """Draw header/footer legal stamps and page numbering on every page."""
    canvas.saveState()

    # Top legal stamp (Red alert)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor("#b91c1c"))  # crimson red
    canvas.drawCentredString(doc.pagesize[0] / 2.0, doc.pagesize[1] - 22, LEGAL_STAMP_TEXT)

    # Top divider
    canvas.setStrokeColor(colors.HexColor("#fca5a5"))
    canvas.setLineWidth(0.5)
    canvas.line(36, doc.pagesize[1] - 26, doc.pagesize[0] - 36, doc.pagesize[1] - 26)

    # Bottom legal stamp
    canvas.drawString(36, 18, LEGAL_STAMP_TEXT)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawRightString(doc.pagesize[0] - 36, 18, f"Page {doc.page}")

    # Bottom divider
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.line(36, 28, doc.pagesize[0] - 36, 28)

    canvas.restoreState()


def generate_section_63_certificate_pdf(
    case_data: Dict[str, Any],
    file_hashes: Dict[str, str],
    officer_data: Optional[Dict[str, Any]] = None,
    system_info: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Generate Section 63 Bharatiya Sakshya Adhiniyam, 2023 certificate draft PDF.
    
    Returns raw PDF bytes.
    Every page is explicitly stamped:
    'DRAFT - for review by legal counsel; verify the prescribed Schedule format before use'
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=38,
        bottomMargin=38,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CertTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        alignment=1,  # Center
    )

    subtitle_style = ParagraphStyle(
        "CertSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e3a8a"),
        alignment=1,
    )

    section_heading = ParagraphStyle(
        "CertSectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=8,
        spaceAfter=3,
    )

    body_style = ParagraphStyle(
        "CertBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )

    body_bold = ParagraphStyle(
        "CertBodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )

    code_style = ParagraphStyle(
        "CertCode",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#0f172a"),
    )

    story = []

    # Title Block
    story.append(Spacer(1, 4))
    story.append(Paragraph("SCHEDULE / FORM OF CERTIFICATE", subtitle_style))
    story.append(Spacer(1, 2))
    story.append(
        Paragraph(
            "CERTIFICATE UNDER SECTION 63 OF THE BHARATIYA SAKSHYA ADHINIYAM, 2023<br/>"
            "FOR ADMISSIBILITY OF ELECTRONIC FORENSIC RECORDS IN EVIDENCE",
            title_style,
        )
    )
    story.append(Spacer(1, 3))
    story.append(
        Paragraph(
            "<i>(Corresponding to erstwhile Section 65B of the Indian Evidence Act, 1872)</i>",
            ParagraphStyle("Subtext", parent=subtitle_style, fontName="Helvetica-Oblique", fontSize=8, textColor=colors.HexColor("#475569")),
        )
    )
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceAfter=6))

    # Case & System Metadata
    ncrp_ref = case_data.get("ncrp_ref", "NCRP/2026/UNASSIGNED")
    victim_utr = case_data.get("victim_utr", "N/A")
    amount_inr = case_data.get("amount_inr")
    amount_str = f"Rs. {amount_inr:,.2f}" if amount_inr else "N/A"
    flagged_addr = case_data.get("flagged_address") or case_data.get("suspect_address") or "N/A"
    chain = case_data.get("chain", "ETH")
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    meta_table_data = [
        [
            Paragraph("<b>NCRP Reference No:</b>", body_style),
            Paragraph(ncrp_ref, body_bold),
            Paragraph("<b>Date & Time of Generation:</b>", body_style),
            Paragraph(gen_time, body_style),
        ],
        [
            Paragraph("<b>Complainant / Victim UTR:</b>", body_style),
            Paragraph(victim_utr, body_style),
            Paragraph("<b>Reported Defrauded Amount:</b>", body_style),
            Paragraph(amount_str, body_bold),
        ],
        [
            Paragraph("<b>Flagged Lead Wallet Address:</b>", body_style),
            Paragraph(flagged_addr, code_style),
            Paragraph("<b>Blockchain Network:</b>", body_style),
            Paragraph(chain, body_style),
        ],
    ]

    meta_table = Table(meta_table_data, colWidths=[120, 160, 130, 130])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # Statement of System Custody and Operation
    story.append(Paragraph("1. IDENTIFICATION OF ELECTRONIC RECORD AND SYSTEM DETAILS", section_heading))
    p1_text = (
        "I hereby certify that the electronic records contained in this cryptographic evidence package, "
        "including the multi-hop forensic trace graph, transaction ledger, attribution analysis, Section 94 BNSS notice, "
        "and investigative report, were produced by the automated computer system detailed below during the ordinary "
        "course of law enforcement forensic investigation:"
    )
    story.append(Paragraph(p1_text, body_style))
    story.append(Spacer(1, 4))

    sys_desc = system_info or {
        "platform": "CryptoTrace Sentinel (SIH26183) — Law Enforcement Blockchain Intelligence Platform",
        "engine_version": "v0.1.0-alpha",
        "hashing_algorithm": "SHA-256 (FIPS PUB 180-4) and RFC 6962 Binary Merkle Tree",
        "host_environment": "Dedicated Cyber Crime Investigation Workstation / Server",
    }

    sys_table_data = [
        [Paragraph("<b>Forensic Application:</b>", body_style), Paragraph(sys_desc.get("platform", ""), body_style)],
        [Paragraph("<b>Engine Version:</b>", body_style), Paragraph(sys_desc.get("engine_version", ""), code_style)],
        [Paragraph("<b>Cryptographic Engine:</b>", body_style), Paragraph(sys_desc.get("hashing_algorithm", ""), code_style)],
        [Paragraph("<b>Operating Environment:</b>", body_style), Paragraph(sys_desc.get("host_environment", ""), body_style)],
    ]
    sys_table = Table(sys_table_data, colWidths=[140, 400])
    sys_table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ])
    )
    story.append(sys_table)
    story.append(Spacer(1, 8))

    # Statutory Declarations under Section 63(2) & 63(4) BSA 2023
    story.append(Paragraph("2. STATUTORY REPRESENTATION AND CUSTODY DECLARATION", section_heading))
    decl_text = (
        "In terms of Section 63(2) and Section 63(4) of the Bharatiya Sakshya Adhiniyam, 2023, I certify that:<br/>"
        "<b>(a)</b> The electronic record was produced by the computer during the period over which the computer was used regularly "
        "to store or process information for the purposes of cyber crime inquiry/investigation.<br/>"
        "<b>(b)</b> Throughout the material period, the computer system was operating properly, or if not, any respect in which it was "
        "not operating properly or was out of operation was not such as to affect the electronic record or the accuracy of its contents.<br/>"
        "<b>(c)</b> The electronic data derived from the blockchain ledger constitutes an unalterable decentralized record of transactions, "
        "and no unauthorized modification, insertion, or deletion has occurred in the forensic outputs.<br/>"
        "<b>(d)</b> The cryptographic hash values enumerated below uniquely identify each component of this electronic evidence package."
    )
    story.append(Paragraph(decl_text, body_style))
    story.append(Spacer(1, 8))

    # Evidence Hashes Table
    story.append(Paragraph("3. SCHEDULE OF ELECTRONIC RECORD ARTIFACTS AND SHA-256 HASHES", section_heading))
    hash_rows = [
        [
            Paragraph("<b>File / Artifact Name</b>", body_bold),
            Paragraph("<b>Cryptographic SHA-256 Checksum</b>", body_bold),
        ]
    ]

    for fname in sorted(file_hashes.keys()):
        hval = file_hashes[fname]
        hash_rows.append([
            Paragraph(f"<code>{fname}</code>", body_style),
            Paragraph(f"<code>{hval}</code>", code_style),
        ])

    hash_table = Table(hash_rows, colWidths=[170, 370])
    hash_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(hash_table)
    story.append(Spacer(1, 10))

    # Signatures & Placeholders Block
    story.append(KeepTogether([
        Paragraph("4. EXECUTION AND ATTESTATION (PLACEHOLDERS)", section_heading),
        Spacer(1, 4),
        Paragraph(
            "<b>PART A: CERTIFICATE BY PERSON IN LAWFUL CHARGE OF COMPUTER SYSTEM / INVESTIGATOR</b>",
            body_bold,
        ),
        Spacer(1, 2),
        Paragraph(
            "I hereby verify and declare that the statements made above are true and correct to the best of my knowledge, "
            "information, and belief, and that I have been in lawful charge of the management / operation of the computer system.",
            body_style,
        ),
        Spacer(1, 6),
        Table([
            [
                Paragraph("<b>Name of Officer:</b>", body_style),
                Paragraph(officer_data.get("full_name", "____________________________________") if officer_data else "____________________________________", body_style),
                Paragraph("<b>Designation / Rank:</b>", body_style),
                Paragraph(officer_data.get("badge_no", "____________________________________") if officer_data else "____________________________________", body_style),
            ],
            [
                Paragraph("<b>Police Station / Unit:</b>", body_style),
                Paragraph(officer_data.get("district", "____________________________________") if officer_data else "____________________________________", body_style),
                Paragraph("<b>P.I.S. / Service ID:</b>", body_style),
                Paragraph("____________________________________", body_style),
            ],
            [
                Paragraph("<b>Date of Signature:</b>", body_style),
                Paragraph("____ / ____ / 202___", body_style),
                Paragraph("<b>Place:</b>", body_style),
                Paragraph("____________________________________", body_style),
            ],
            [
                Paragraph("<b>Signature:</b>", body_style),
                Paragraph("____________________________________", body_style),
                Paragraph("<b>Official Stamp / Seal:</b>", body_style),
                Paragraph("____________________________________", body_style),
            ],
        ], colWidths=[110, 160, 110, 160], style=[
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]),
        Spacer(1, 10),
        Paragraph(
            "<b>PART B: CERTIFICATE BY FORENSIC EXPERT (SECTION 39(2) & 63 BSA 2023, WHERE APPLICABLE)</b>",
            body_bold,
        ),
        Spacer(1, 2),
        Paragraph(
            "Certified that I have examined the cryptographic hashes and automated forensic output generation pipeline, "
            "and confirm that the digital evidence corresponds with the reported blockchain transaction records.",
            body_style,
        ),
        Spacer(1, 6),
        Table([
            [
                Paragraph("<b>Name of Expert:</b>", body_style),
                Paragraph("____________________________________", body_style),
                Paragraph("<b>Designation:</b>", body_style),
                Paragraph("____________________________________", body_style),
            ],
            [
                Paragraph("<b>Forensic Laboratory:</b>", body_style),
                Paragraph("____________________________________", body_style),
                Paragraph("<b>Accreditation / Notif.:</b>", body_style),
                Paragraph("____________________________________", body_style),
            ],
            [
                Paragraph("<b>Signature of Expert:</b>", body_style),
                Paragraph("____________________________________", body_style),
                Paragraph("<b>Date & Official Seal:</b>", body_style),
                Paragraph("____ / ____ / 202___  [SEAL]", body_style),
            ],
        ], colWidths=[110, 160, 110, 160], style=[
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]),
    ]))

    doc.build(story, onFirstPage=_draw_page_decorations, onLaterPages=_draw_page_decorations)
    return buffer.getvalue()
