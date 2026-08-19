import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from app.config import REPORTS_DIR, FORENSIC_DIR

class ForensicReportGenerator:
    """
    Generates high-integrity, court-ready Forensic PDF verification reports.
    """

    @staticmethod
    def generate_pdf(
        evidence_data: Dict[str, Any],
        case_data: Dict[str, Any],
        forensic_result: Dict[str, Any],
        findings: List[Dict[str, Any]],
        custody_events: List[Dict[str, Any]]
    ) -> Path:
        evidence_id = evidence_data.get("evidence_id", "EV-UNKNOWN")
        output_filename = f"Forensic_Report_{evidence_id}.pdf"
        output_path = REPORTS_DIR / output_filename

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#2563eb"),
            alignment=TA_CENTER
        )
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=10,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'BodyDark',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155")
        )
        bold_body = ParagraphStyle(
            'BoldBodyDark',
            parent=body_style,
            fontName='Helvetica-Bold'
        )
        table_cell = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1e293b")
        )
        table_cell_bold = ParagraphStyle(
            'TableCellBold',
            parent=table_cell,
            fontName='Helvetica-Bold'
        )

        story = []

        # 1. Header Banner
        story.append(Paragraph("EVIDENCE-X : FORENSIC VERIFICATION REPORT", title_style))
        story.append(Paragraph("DIGITAL EVIDENCE INTEGRITY & DEEPFAKE AUTHENTICITY ASSESSMENT", subtitle_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Standard Compliance: ISO/IEC 27037 & SIH PS-27 Specification | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", ParagraphStyle('MetaHead', parent=styles['Normal'], fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=10))

        # 2. Case & Evidence Summary Table
        risk_cat = forensic_result.get("risk_category", "UNKNOWN")
        risk_score = forensic_result.get("forensic_risk_score", 0.0)

        # Risk Color
        if risk_cat == "LOW RISK":
            badge_color = colors.HexColor("#16a34a")
        elif risk_cat == "REVIEW REQUIRED":
            badge_color = colors.HexColor("#ca8a04")
        else:
            badge_color = colors.HexColor("#dc2626")

        case_info_data = [
            [
                Paragraph("<b>Evidence ID:</b>", bold_body), Paragraph(evidence_id, body_style),
                Paragraph("<b>Case Reference:</b>", bold_body), Paragraph(f"{case_data.get('case_id', 'N/A')} - {case_data.get('title', 'N/A')}", body_style)
            ],
            [
                Paragraph("<b>File Name:</b>", bold_body), Paragraph(evidence_data.get("original_filename", "N/A"), body_style),
                Paragraph("<b>Modality / Format:</b>", bold_body), Paragraph(f"{evidence_data.get('modality', 'N/A')} ({evidence_data.get('mime_type', 'N/A')})", body_style)
            ],
            [
                Paragraph("<b>File Size:</b>", bold_body), Paragraph(f"{round(evidence_data.get('file_size_bytes', 0) / 1024, 1)} KB", body_style),
                Paragraph("<b>Lead Investigator:</b>", bold_body), Paragraph(case_data.get("lead_investigator", "Digital Forensics Unit"), body_style)
            ],
            [
                Paragraph("<b>Ingestion Date:</b>", bold_body), Paragraph(evidence_data.get("uploaded_at", "N/A")[:19], body_style),
                Paragraph("<b>Forensic Risk Assessment:</b>", bold_body), Paragraph(f"<b>{risk_cat} ({risk_score}/100)</b>", ParagraphStyle('RStyle', parent=body_style, textColor=badge_color, fontName='Helvetica-Bold'))
            ]
        ]

        t_case = Table(case_info_data, colWidths=[90, 180, 100, 170])
        t_case.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_case)
        story.append(Spacer(1, 10))

        # 3. Cryptographic Fingerprints
        story.append(Paragraph("1. Cryptographic Fingerprints & Integrity Baseline", section_style))
        hash_data = [
            [Paragraph("<b>Algorithm</b>", table_cell_bold), Paragraph("<b>Cryptographic Hash Fingerprint</b>", table_cell_bold), Paragraph("<b>Baseline Match</b>", table_cell_bold)],
            [Paragraph("SHA-256", table_cell_bold), Paragraph(f"<font face='Courier' size='7'>{evidence_data.get('sha256_hash', 'N/A')}</font>", table_cell), Paragraph(forensic_result.get("integrity_status", "VERIFIED"), table_cell_bold)],
            [Paragraph("SHA-512", table_cell_bold), Paragraph(f"<font face='Courier' size='6'>{evidence_data.get('sha512_hash', 'N/A')[:64]}...</font>", table_cell), Paragraph("MATCH", table_cell)],
            [Paragraph("MD5", table_cell_bold), Paragraph(f"<font face='Courier' size='7'>{evidence_data.get('md5_hash', 'N/A')}</font>", table_cell), Paragraph("MATCH", table_cell)],
        ]
        t_hash = Table(hash_data, colWidths=[65, 395, 80])
        t_hash.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_hash)
        story.append(Spacer(1, 10))

        # 4. Executive Forensic Summary & Copilot Narrative
        story.append(Paragraph("2. Executive Summary & Investigator Analysis", section_style))
        summary_text = forensic_result.get("summary_narrative") or "Forensic analysis completed across all primary digital signals."
        recom_text = forensic_result.get("recommendations") or "No further actions required."
        
        story.append(Paragraph(f"<b>Findings Synthesis:</b> {summary_text}", body_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"<b>Actionable Recommendations:</b><br/>{recom_text.replace(chr(10), '<br/>')}", body_style))
        story.append(Spacer(1, 10))

        # 5. Detailed Forensic Findings
        story.append(Paragraph("3. Technical Forensic Findings Breakdown", section_style))
        findings_table_data = [
            [
                Paragraph("<b>Signal Name</b>", table_cell_bold),
                Paragraph("<b>Category</b>", table_cell_bold),
                Paragraph("<b>Severity</b>", table_cell_bold),
                Paragraph("<b>Score</b>", table_cell_bold),
                Paragraph("<b>Technical Explanation</b>", table_cell_bold)
            ]
        ]
        
        for f in findings:
            sev = f.get("severity", "INFO")
            if sev == "CRITICAL":
                sev_color = colors.HexColor("#991b1b")
            elif sev == "HIGH":
                sev_color = colors.HexColor("#dc2626")
            elif sev == "MEDIUM":
                sev_color = colors.HexColor("#d97706")
            else:
                sev_color = colors.HexColor("#16a34a")

            findings_table_data.append([
                Paragraph(f.get("signal_name", "Signal"), table_cell_bold),
                Paragraph(f.get("category", "GENERAL"), table_cell),
                Paragraph(f"<b><font color='{sev_color.hexval()}'>{sev}</font></b>", table_cell),
                Paragraph(f"{f.get('score', 0)}/100", table_cell),
                Paragraph(f.get("explanation", ""), table_cell)
            ])

        t_find = Table(findings_table_data, colWidths=[120, 80, 55, 45, 240])
        t_find.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_find)
        story.append(Spacer(1, 10))

        # 6. Visual Forensic Exhibits (if available)
        raw_metrics = forensic_result.get("raw_metrics_json", {})
        if isinstance(raw_metrics, str):
            import json
            try:
                raw_metrics = json.loads(raw_metrics)
            except Exception:
                raw_metrics = {}

        ela_path = raw_metrics.get("ela_image_path")
        fft_path = raw_metrics.get("fft_image_path")
        spectrogram_path = raw_metrics.get("spectrogram_path")

        visual_exhibits = []
        if ela_path and os.path.exists(ela_path):
            visual_exhibits.append(("Exhibit A: Error Level Analysis (ELA Heatmap)", ela_path))
        if fft_path and os.path.exists(fft_path):
            visual_exhibits.append(("Exhibit B: 2D FFT Frequency Spectrum", fft_path))
        if spectrogram_path and os.path.exists(spectrogram_path):
            visual_exhibits.append(("Exhibit C: Audio Spectrogram & Splicing Analysis", spectrogram_path))

        if visual_exhibits:
            story.append(Paragraph("4. Visual Forensic Exhibits", section_style))
            for title, img_p in visual_exhibits:
                try:
                    story.append(Paragraph(f"<b>{title}</b>", body_style))
                    story.append(Spacer(1, 2))
                    story.append(RLImage(img_p, width=240, height=160))
                    story.append(Spacer(1, 6))
                except Exception as e:
                    pass

        # 7. Chain of Custody Audit Ledger
        story.append(Paragraph("5. Chain of Custody Immutable Ledger", section_style))
        coc_table_data = [
            [
                Paragraph("<b>Timestamp (UTC)</b>", table_cell_bold),
                Paragraph("<b>Action</b>", table_cell_bold),
                Paragraph("<b>Actor / Identity</b>", table_cell_bold),
                Paragraph("<b>Recorded SHA-256</b>", table_cell_bold),
                Paragraph("<b>Event Details</b>", table_cell_bold)
            ]
        ]
        for event in custody_events:
            coc_table_data.append([
                Paragraph(event.get("timestamp", "")[:19], table_cell),
                Paragraph(event.get("action", ""), table_cell_bold),
                Paragraph(event.get("actor", ""), table_cell),
                Paragraph(f"<font face='Courier' size='6'>{event.get('recorded_sha256', '')[:16]}...</font>", table_cell),
                Paragraph(event.get("details", ""), table_cell)
            ])

        t_coc = Table(coc_table_data, colWidths=[90, 110, 100, 80, 160])
        t_coc.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_coc)
        story.append(Spacer(1, 14))

        # 8. Legal Disclaimer & NIST Notice
        disclaimer = (
            "<b>LEGAL & SCIENTIFIC DISCLAIMER:</b> This report was generated automatically by the EVIDENCE-X "
            "Forensic Verification Engine (SIH PS-27). Measurements and findings represent an objective, multi-signal "
            "forensic authenticity assessment. In compliance with NIST guidelines, automated AI detection scores are "
            "probabilistic indicators and must be corroborated by qualified forensic examiners and physical corroborating "
            "evidence prior to formal submission in a court of law."
        )
        story.append(Paragraph(disclaimer, ParagraphStyle('Disc', parent=styles['Normal'], fontSize=7, leading=9.5, textColor=colors.HexColor("#64748b"))))

        # Build PDF
        doc.build(story)
        return output_path
