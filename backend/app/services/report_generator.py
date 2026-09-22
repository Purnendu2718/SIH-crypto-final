"""PDF Evidence Package Generator using pure ReportLab.
Produces a court-ready, defensible electronic forensic report including:
- Case header
- Methods & limitations (heuristics glossary, taint model assumptions, 'Attribution is not proof')
- Trace parameters
- Summary of endpoints and circular flow cycles
- Table of key transfers with transaction hashes (txids)
- Label table with sources and confidence
- Appendix listing evidence hashes, where every claim references an evidence artifact ID
- RFC 3161 external timestamp anchoring status (or 'not externally anchored')

Reference: SIH26183, Ministry of Home Affairs / I4C, Section 94 BNSS.
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


def _draw_report_footer(canvas, doc):
    """Draw footer page numbers and defensibility statement on every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#64748b"))
    canvas.drawString(36, 20, "CryptoTrace Sentinel • Defensible Forensics Engine • 'Attribution is not proof'")
    canvas.drawRightString(doc.pagesize[0] - 36, 20, f"Page {doc.page}")
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.setLineWidth(0.5)
    canvas.line(36, 28, doc.pagesize[0] - 36, 28)
    canvas.restoreState()


def generate_pdf_evidence_report(
    case_data: Dict[str, Any],
    forensic_data: Dict[str, Any],
    evidence_hashes: Dict[str, str],
    officer_data: Optional[Dict[str, Any]] = None,
    trace_params: Optional[Dict[str, Any]] = None,
    tsa_status: Optional[str] = None,
) -> bytes:
    """Generate a high-fidelity, court-defensible PDF forensic evidence report.
    Returns binary PDF bytes. Pure Python (ReportLab).
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

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#0f172a"),
        alignment=1,  # Center
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e3a8a"),
        alignment=1,
    )

    section_heading = ParagraphStyle(
        "SectionHeading",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=8,
        spaceAfter=3,
    )

    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#1e293b"),
    )

    body_bold = ParagraphStyle(
        "BodyBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#0f172a"),
    )

    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=6.5,
        leading=8.5,
        textColor=colors.HexColor("#0f172a"),
    )

    alert_banner_style = ParagraphStyle(
        "AlertBanner",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#991b1b"),
        alignment=1,
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("CYBER CRIME FORENSICS DIVISION • LAW ENFORCEMENT INTELLIGENCE", subtitle_style))
    story.append(Spacer(1, 2))
    story.append(Paragraph("CRYPTOTRACE SENTINEL — FORENSIC EVIDENCE REPORT", title_style))
    story.append(
        Paragraph("Court-Defensible Multi-Hop Blockchain Tracing &amp; Off-Ramp Attribution (SIH26183)", subtitle_style)
    )
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=6))

    # Mandatory Legal Notice Banner
    story.append(
        Table(
            [
                [
                    Paragraph(
                        "<b>DEFENSIBILITY NOTICE:</b> Attribution is decision-support intelligence, not proof of individual culpability. "
                        "All attributions carry explainable confidence scores. Every claim references an underlying cryptographic evidence artifact.",
                        alert_banner_style,
                    )
                ]
            ],
            colWidths=[540],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#f87171")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ],
        )
    )
    story.append(Spacer(1, 6))

    # 2. Case & Investigating Officer Details
    officer = officer_data or {}
    ncrp_ref = case_data.get("ncrp_ref", "NCRP/2026/UNASSIGNED")
    victim_utr = case_data.get("victim_utr", "N/A")
    amount_inr = case_data.get("amount_inr")
    inr_str = f"INR {amount_inr:,.2f}" if amount_inr else "Not Specified"
    lead_addr = case_data.get("flagged_address") or case_data.get("suspect_address") or "N/A"
    chain = case_data.get("chain", "ETH")
    date_str = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S UTC")

    meta_table_data = [
        [
            Paragraph("<b>NCRP Reference No:</b>", body_style),
            Paragraph(ncrp_ref, body_bold),
            Paragraph("<b>Date of Report:</b>", body_style),
            Paragraph(date_str, body_style),
        ],
        [
            Paragraph("<b>Complainant / Victim UTR:</b>", body_style),
            Paragraph(victim_utr, body_style),
            Paragraph("<b>Reported Defrauded Amount:</b>", body_style),
            Paragraph(inr_str, body_bold),
        ],
        [
            Paragraph("<b>Flagged Lead Wallet Address:</b>", body_style),
            Paragraph(lead_addr, code_style),
            Paragraph("<b>Blockchain Network:</b>", body_style),
            Paragraph(chain, body_style),
        ],
        [
            Paragraph("<b>Investigating Officer:</b>", body_style),
            Paragraph(officer.get("full_name", "Investigating Officer"), body_bold),
            Paragraph("<b>Badge &amp; District:</b>", body_style),
            Paragraph(f"{officer.get('badge_no', 'N/A')} • {officer.get('district', 'Cyber Cell')}", body_style),
        ],
    ]

    meta_table = Table(meta_table_data, colWidths=[130, 150, 110, 150])
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
    story.append(Spacer(1, 6))

    # 3. Methods & Limitations (Glossary & Taint Assumptions)
    story.append(Paragraph("1. METHODS, FORENSIC LIMITATIONS &amp; HEURISTICS GLOSSARY", section_heading))
    story.append(
        Paragraph(
            "<b>Forensic Method:</b> Multi-hop graph traversal combining on-chain heuristics, VASP cluster directory matching, "
            "temporal correlation, and FIFO contamination accounting. <i>[Ref: artifact_methods_manifest]</i>",
            body_style,
        )
    )
    story.append(Spacer(1, 3))

    glossary_data = [
        [Paragraph("<b>Forensic Heuristic</b>", body_bold), Paragraph("<b>Definition &amp; Investigative Relevance</b>", body_bold)],
        [
            Paragraph("<b>SWEEP</b>", body_bold),
            Paragraph("Automated consolidation transfer moving funds from temporary deposit wallets into pooled exchange hot wallets. Strong indicator of VASP credit.", body_style),
        ],
        [
            Paragraph("<b>FAN_OUT</b>", body_bold),
            Paragraph("Rapid distribution of funds from one source address across multiple intermediaries (1:N split) to evade transaction thresholds.", body_style),
        ],
        [
            Paragraph("<b>MIXER</b>", body_bold),
            Paragraph("Privacy tumbler protocol (e.g. Tornado Cash) designed to deliberately sever the on-chain cryptographic link between depositors and recipients.", body_style),
        ],
        [
            Paragraph("<b>PEELING_CHAIN</b>", body_bold),
            Paragraph("Linear succession of transactions where a small amount is peeled off at each hop while the remaining majority moves to a fresh change address.", body_style),
        ],
        [
            Paragraph("<b>LAYERING</b>", body_bold),
            Paragraph("Multi-hop fund movements through benign or mule intermediary wallets to distance illicit proceeds from origin crime.", body_style),
        ],
        [
            Paragraph("<b>CROSS_CHAIN_BRIDGE</b>", body_bold),
            Paragraph("Smart contract escrow locking assets on one blockchain (e.g. Ethereum) and minting/releasing tokens on another (e.g. TRON).", body_style),
        ],
        [
            Paragraph("<b>FIFO TAINT MODEL</b>", body_bold),
            Paragraph("First-In, First-Out contamination tracking assumes tainted stolen funds leave an account first in the order deposits arrived.", body_style),
        ],
    ]
    glossary_table = Table(glossary_data, colWidths=[120, 420])
    glossary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(glossary_table)
    story.append(Spacer(1, 6))

    # 4. Trace Parameters & Scope
    story.append(Paragraph("2. INVESTIGATION PARAMETERS &amp; RUN CONFIGURATION", section_heading))
    params = trace_params or {}
    params_data = [
        [
            Paragraph("<b>Seed Lead Address:</b>", body_style),
            Paragraph(params.get("seed_address", lead_addr), code_style),
            Paragraph("<b>Max Traversal Hops:</b>", body_style),
            Paragraph(str(params.get("max_hops", 3)), body_style),
        ],
        [
            Paragraph("<b>Taint Model:</b>", body_style),
            Paragraph(f"{params.get('taint_model', 'FIFO')} Accounting", body_bold),
            Paragraph("<b>Dust Filter Threshold:</b>", body_style),
            Paragraph(f"{params.get('min_amount', 0.0)} {chain}", body_style),
        ],
        [
            Paragraph("<b>Date Window:</b>", body_style),
            Paragraph(f"{params.get('start_date', 'Genesis')} to {params.get('end_date', 'Present')}", body_style),
            Paragraph("<b>Data Evidence Source:</b>", body_style),
            Paragraph(params.get("source", "Verified On-Chain Adapter Ledger"), body_style),
        ],
    ]
    params_table = Table(params_data, colWidths=[120, 160, 120, 140])
    params_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(params_table)
    story.append(Spacer(1, 6))

    # 5. Destination VASP Attribution & Summary of Endpoints & Cycles
    story.append(Paragraph("3. ATTRIBUTION, ENDPOINTS &amp; CIRCULAR FLOW SUMMARY", section_heading))
    attr = forensic_data.get("attribution", {})
    matched_vasp = attr.get("matched_entity", "Insufficient Evidence")
    confidence = attr.get("confidence", 0.0)
    band = attr.get("confidence_band", "INSUFFICIENT_EVIDENCE")
    rule = attr.get("rule_fired", "HEURISTIC_SEARCH")

    trace_info = forensic_data.get("trace", {})
    paths = trace_info.get("paths", [])
    total_hops = trace_info.get("total_hops", len(paths))

    # Detect endpoints (outDegree == 0) and cycles
    all_from = {p["from_addr"].lower() for p in paths}
    all_to = {p["to_addr"].lower() for p in paths}
    endpoints_set = all_to - all_from
    endpoints_count = len(endpoints_set)

    # Cycles
    cycles_detected = forensic_data.get("cycles", [])
    cycles_count = len(cycles_detected)

    summary_table_data = [
        [
            Paragraph("<b>Attributed Receiving VASP:</b>", body_style),
            Paragraph(f"<b>{matched_vasp}</b>", body_bold),
            Paragraph("<b>Confidence Band:</b>", body_style),
            Paragraph(f"<b>{band} ({round(confidence * 100, 1)}%)</b>", body_bold),
        ],
        [
            Paragraph("<b>Primary Attribution Rule:</b>", body_style),
            Paragraph(rule, code_style),
            Paragraph("<b>Attribution Claim Ref:</b>", body_style),
            Paragraph("<code>[Artifact ID: raw_trace_payload]</code>", code_style),
        ],
        [
            Paragraph("<b>Identified Terminal Endpoints:</b>", body_style),
            Paragraph(f"{endpoints_count} terminal recipient address(es)", body_style),
            Paragraph("<b>Circular Flow Cycles:</b>", body_style),
            Paragraph(f"{cycles_count} cycle(s) detected", body_bold if cycles_count > 0 else body_style),
        ],
        [
            Paragraph("<b>Total Forensic Hops:</b>", body_style),
            Paragraph(f"{total_hops} hop(s) traversed", body_style),
            Paragraph("<b>VASP Off-Ramp Status:</b>", body_style),
            Paragraph("REACHED OFF-RAMP" if trace_info.get("reached_vasp") else "IN-FLIGHT", body_bold),
        ],
    ]
    summary_table = Table(summary_table_data, colWidths=[140, 140, 120, 140])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#93c5fd")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bfdbfe")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(summary_table)
    story.append(Spacer(1, 6))

    # 6. Table of Key Transfers with Txids
    story.append(Paragraph("4. TABLE OF KEY ON-CHAIN TRANSFERS &amp; TXIDS", section_heading))
    story.append(
        Paragraph(
            "Each transfer listed below represents a verified transaction from the ledger. <i>[Ref: artifact_raw_transactions]</i>",
            body_style,
        )
    )
    story.append(Spacer(1, 3))

    tx_table_data = [
        [
            Paragraph("<b>Hop</b>", body_bold),
            Paragraph("<b>From Address</b>", body_bold),
            Paragraph("<b>To Address</b>", body_bold),
            Paragraph("<b>Value</b>", body_bold),
            Paragraph("<b>Transaction Hash (TxID)</b>", body_bold),
        ]
    ]

    for p in paths:
        f_addr = p.get("from_addr", "")
        t_addr = p.get("to_addr", "")
        f_short = f"{f_addr[:10]}...{f_addr[-6:]}" if len(f_addr) > 20 else f_addr
        t_short = f"{t_addr[:10]}...{t_addr[-6:]}" if len(t_addr) > 20 else t_addr
        txid = p.get("tx_hash", "—")
        tx_short = f"{txid[:16]}...{txid[-8:]}" if len(txid) > 28 else txid
        val_str = f"{p.get('value', 0)} {p.get('chain', chain)}"

        tx_table_data.append([
            Paragraph(str(p.get("hop_index", 1)), body_style),
            Paragraph(f_short, code_style),
            Paragraph(t_short, code_style),
            Paragraph(val_str, body_style),
            Paragraph(tx_short, code_style),
        ])

    tx_table = Table(tx_table_data, colWidths=[30, 125, 125, 75, 185])
    tx_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(tx_table)
    story.append(Spacer(1, 6))

    # 7. Label Table with Sources and Confidence
    story.append(Paragraph("5. ENTITY LABELS &amp; CONFIDENCE BREAKDOWN", section_heading))
    label_table_data = [
        [
            Paragraph("<b>Entity / Label Name</b>", body_bold),
            Paragraph("<b>Category</b>", body_bold),
            Paragraph("<b>Source Registry</b>", body_bold),
            Paragraph("<b>Rule Fired</b>", body_bold),
            Paragraph("<b>Confidence</b>", body_bold),
            Paragraph("<b>Artifact ID</b>", body_bold),
        ],
        [
            Paragraph(f"<b>{matched_vasp}</b>", body_style),
            Paragraph("Exchange / VASP", body_style),
            Paragraph("FIU-IND VASP Directory", body_style),
            Paragraph(rule, code_style),
            Paragraph(f"{round(confidence * 100, 1)}% ({band})", body_bold),
            Paragraph("<code>artifact_vasp_directory</code>", code_style),
        ],
    ]

    typos = forensic_data.get("typologies", [])
    for t in typos:
        label_table_data.append([
            Paragraph(f"<b>Typology: {t.get('typology')}</b>", body_style),
            Paragraph("Laundering Pattern", body_style),
            Paragraph("Forensic Typology Engine", body_style),
            Paragraph(t.get("typology", "TYPOLOGY_RULE"), code_style),
            Paragraph("Rule-Based Match", body_style),
            Paragraph("<code>artifact_raw_trace_payload</code>", code_style),
        ])

    label_table = Table(label_table_data, colWidths=[110, 80, 100, 100, 75, 75])
    label_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(label_table)
    story.append(Spacer(1, 6))

    # 8. Appendix: Evidence Hashes & External Timestamp Status
    story.append(Paragraph("6. APPENDIX: EVIDENCE ARTIFACT HASHES &amp; INTEGRITY ANCHOR", section_heading))
    timestamp_desc = (
        f"RFC 3161 Timestamp Token Attached (Anchor: {tsa_status})"
        if tsa_status
        else "not externally anchored"
    )

    story.append(
        Paragraph(
            f"<b>External Timestamp Status:</b> {timestamp_desc}<br/>"
            "Every artifact listed below has been hashed using SHA-256 and recorded in <code>MANIFEST.json</code>. "
            "To verify integrity independently, run <code>python verify.py</code> on the evidence package.",
            body_style,
        )
    )
    story.append(Spacer(1, 4))

    hash_rows = [
        [
            Paragraph("<b>Artifact / File Name</b>", body_bold),
            Paragraph("<b>Artifact Identifier</b>", body_bold),
            Paragraph("<b>Cryptographic SHA-256 Digest</b>", body_bold),
        ]
    ]

    for fname, fhash in sorted(evidence_hashes.items()):
        art_id = f"artifact_{fname.replace('.', '_').replace('/', '_')}"
        hash_rows.append([
            Paragraph(f"<code>{fname}</code>", body_style),
            Paragraph(f"<code>{art_id}</code>", code_style),
            Paragraph(f"<code>{fhash}</code>", code_style),
        ])

    hash_table = Table(hash_rows, colWidths=[140, 120, 280])
    hash_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ])
    )
    story.append(hash_table)

    doc.build(story, onFirstPage=_draw_report_footer, onLaterPages=_draw_report_footer)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
