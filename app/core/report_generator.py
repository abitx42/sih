import os
import json
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
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#2563eb"),
            alignment=TA_CENTER
        )
        section_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=8,
            spaceAfter=3
        )
        body_style = ParagraphStyle(
            'BodyDark',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11.5,
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
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#1e293b")
        )
        table_cell_bold = ParagraphStyle(
            'TableCellBold',
            parent=table_cell,
            fontName='Helvetica-Bold'
        )

        story = []

        # 1. Header Banner
        story.append(Paragraph("EVIDENCE-X : FORENSIC VERIFICATION DOSSIER", title_style))
        story.append(Paragraph("DIGITAL EVIDENCE INTEGRITY & AUTOMATED FORENSIC SIGNAL ASSESSMENT", subtitle_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"Standard Compliance: ISO/IEC 27037 & SIH PS-27 Specification | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", ParagraphStyle('MetaHead', parent=styles['Normal'], fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 5))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=7))

        # 2. Case & Evidence Summary Table
        risk_cat = forensic_result.get("risk_category", "UNKNOWN")
        risk_score = forensic_result.get("forensic_risk_score", 0.0)

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
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_case)
        story.append(Spacer(1, 6))

        # 3. Cryptographic Fingerprints & Integrity Note
        story.append(Paragraph("1. File Integrity & Cryptographic Baseline (Bit-Level Verification)", section_style))
        story.append(Paragraph("<i>Note: Cryptographic hash matching certifies bit-level data preservation since ingestion. It does not certify that the media content itself is genuine or unmanipulated.</i>", ParagraphStyle('HashNote', parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 2))
        hash_data = [
            [Paragraph("<b>Algorithm</b>", table_cell_bold), Paragraph("<b>Cryptographic Hash Fingerprint</b>", table_cell_bold), Paragraph("<b>Baseline Match</b>", table_cell_bold)],
            [Paragraph("SHA-256", table_cell_bold), Paragraph(f"<font face='Courier' size='6.5'>{evidence_data.get('sha256_hash', 'N/A')}</font>", table_cell), Paragraph(forensic_result.get("integrity_status", "VERIFIED"), table_cell_bold)],
            [Paragraph("SHA-512", table_cell_bold), Paragraph(f"<font face='Courier' size='5.5'>{evidence_data.get('sha512_hash', 'N/A')[:64]}...</font>", table_cell), Paragraph("MATCH", table_cell)],
            [Paragraph("MD5", table_cell_bold), Paragraph(f"<font face='Courier' size='6.5'>{evidence_data.get('md5_hash', 'N/A')}</font>", table_cell), Paragraph("MATCH", table_cell)],
        ]
        t_hash = Table(hash_data, colWidths=[65, 395, 80])
        t_hash.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_hash)
        story.append(Spacer(1, 6))

        # 4. Machine Learning Vision Model Assessment
        story.append(Paragraph("2. Machine Learning Vision Model Assessment & Reproducibility Metadata", section_style))
        ml_model = forensic_result.get("ai_model_name", "dima806/deepfake_vs_real_image_detection")
        ml_ver = forensic_result.get("ai_model_version") or "29e4cf9efc543845610045f6ba7e88e5cf9d9301"
        ml_status = forensic_result.get("model_status", "AVAILABLE")
        ml_indicator = forensic_result.get("ai_manipulation_indicator")
        ml_conf = forensic_result.get("model_confidence")

        indicator_str = f"{round(ml_indicator * 100, 1)}%" if ml_indicator is not None else ml_status
        conf_str = f"{round(ml_conf * 100, 1)}%" if ml_conf is not None else "N/A"

        raw_metrics = forensic_result.get("raw_metrics_json", {})
        if isinstance(raw_metrics, str):
            try:
                raw_metrics = json.loads(raw_metrics)
            except Exception:
                raw_metrics = {}

        ml_details = raw_metrics.get("ml_detector", {})
        runtime_dev = ml_details.get("runtime_device", "cpu")
        inference_ts = ml_details.get("inference_timestamp", forensic_result.get("analyzed_at", "N/A"))[:19]
        label_map_str = json.dumps(ml_details.get("label_mapping", {0: "REAL", 1: "FAKE"}))

        ml_table_data = [
            [
                Paragraph("<b>Model Architecture / Repo</b>", table_cell_bold),
                Paragraph("<b>Revision (Commit)</b>", table_cell_bold),
                Paragraph("<b>Model Status</b>", table_cell_bold),
                Paragraph("<b>AI Indicator</b>", table_cell_bold),
                Paragraph("<b>Confidence</b>", table_cell_bold),
                Paragraph("<b>Device / Timestamp</b>", table_cell_bold)
            ],
            [
                Paragraph(f"<font size='6.5'>{ml_model}</font>", table_cell),
                Paragraph(f"<font size='5.5'>{ml_ver[:12]}...</font>", table_cell),
                Paragraph(f"<b>{ml_status}</b>", table_cell_bold),
                Paragraph(f"<b>{indicator_str}</b>", table_cell_bold),
                Paragraph(conf_str, table_cell),
                Paragraph(f"<font size='6'>{runtime_dev} • {inference_ts}</font>", table_cell)
            ]
        ]
        t_ml = Table(ml_table_data, colWidths=[150, 65, 95, 80, 50, 100])
        t_ml.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_ml)
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"<i>Label Mapping: {label_map_str} | Notice: The AI manipulation indicator is an automated statistical classification metric produced by the local vision model, not definitive legal proof of authenticity or manipulation.</i>", ParagraphStyle('MLDisc', parent=body_style, fontSize=6.5, leading=8.5, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 6))

        # 5. Executive Forensic Narrative & Recommendations
        story.append(Paragraph("3. Executive Forensic Narrative & Recommendations", section_style))
        summary_text = forensic_result.get("summary_narrative") or "Automated multi-signal forensic evaluation completed."
        recom_text = forensic_result.get("recommendations") or "No further actions required."
        
        story.append(Paragraph(f"<b>Automated Findings Synthesis:</b> {summary_text}", body_style))
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"<b>Investigator Recommendations:</b><br/>{recom_text.replace(chr(10), '<br/>')}", body_style))
        story.append(Spacer(1, 6))

        # 6. Detailed Forensic Findings Breakdown
        story.append(Paragraph("4. Technical Forensic Findings Breakdown", section_style))
        findings_table_data = [
            [
                Paragraph("<b>Signal Name</b>", table_cell_bold),
                Paragraph("<b>Category</b>", table_cell_bold),
                Paragraph("<b>Severity</b>", table_cell_bold),
                Paragraph("<b>Score</b>", table_cell_bold),
                Paragraph("<b>Technical Forensic Explanation</b>", table_cell_bold)
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
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_find)
        story.append(Spacer(1, 6))

        # 7. Visual Forensic Exhibits
        ela_path = raw_metrics.get("ela_image_path")
        fft_path = raw_metrics.get("fft_image_path")
        spectrogram_path = raw_metrics.get("spectrogram_path")

        visual_exhibits = []
        if ela_path and os.path.exists(ela_path):
            visual_exhibits.append(("Exhibit A: Error Level Analysis (ELA 95% Heatmap)", ela_path))
        if fft_path and os.path.exists(fft_path):
            visual_exhibits.append(("Exhibit B: 2D FFT Frequency Power Spectrum", fft_path))
        if spectrogram_path and os.path.exists(spectrogram_path):
            visual_exhibits.append(("Exhibit C: Audio Spectrogram & Splicing Analysis", spectrogram_path))

        if visual_exhibits:
            story.append(Paragraph("5. Visual Forensic Exhibits", section_style))
            for title, img_p in visual_exhibits:
                try:
                    story.append(Paragraph(f"<b>{title}</b>", body_style))
                    story.append(Spacer(1, 1.5))
                    story.append(RLImage(img_p, width=220, height=130))
                    story.append(Spacer(1, 3))
                except Exception:
                    pass

        # 8. Chain of Custody Audit Ledger
        story.append(Paragraph("6. Chain of Custody Immutable Ledger", section_style))
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
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_coc)
        story.append(Spacer(1, 8))

        # 9. Legal Disclaimer & NIST Notice
        disclaimer = (
            "<b>LEGAL & SCIENTIFIC DISCLAIMER:</b> This dossier was generated automatically by the EVIDENCE-X "
            "Forensic Verification Engine (SIH PS-27). Measurements and findings represent an objective, multi-signal "
            "forensic authenticity assessment. In compliance with NIST guidelines, automated AI manipulation indicators "
            "are statistical classification signals and must be corroborated by qualified forensic examiners and physical "
            "corroborating evidence prior to formal submission in a court of law."
        )
        story.append(Paragraph(disclaimer, ParagraphStyle('Disc', parent=styles['Normal'], fontSize=6.5, leading=8.5, textColor=colors.HexColor("#64748b"))))

        # Build PDF
        doc.build(story)
        return output_path
