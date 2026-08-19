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
        output_filename = f"truth_lens_report_{evidence_id}.pdf"
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
            'DocSection',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=8,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'DocBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
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
        story.append(Paragraph("TRUTH LENS : DIGITAL EVIDENCE FORENSIC ASSESSMENT REPORT", title_style))
        story.append(Paragraph("AUTOMATED MULTI-SIGNAL SCREENING DOSSIER & INVESTIGATOR REVIEW AID", subtitle_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"Truth Lens Forensic Assessment Report | Prototype Review Aid (SIH PS-27) | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", ParagraphStyle('MetaHead', parent=styles['Normal'], fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))))
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
        story.append(Paragraph("1. File Cryptographic Fingerprint & Baseline Fidelity", section_style))
        story.append(Paragraph("<i>Note: Cryptographic hash calculation records bit-level data preservation since ingestion. It does not certify that the media content itself is genuine or unmanipulated. 'MATCH' indicates verification against an external reference hash; 'RECORDED BASELINE' indicates fingerprint calculated at initial intake.</i>", ParagraphStyle('HashNote', parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 2))
        sha256_val = evidence_data.get("sha256_hash")
        sha512_val = evidence_data.get("sha512_hash")
        md5_val = evidence_data.get("md5_hash")

        integrity_str = forensic_result.get("integrity_status", "RECORDED")
        
        def get_match_status(hash_val):
            if not hash_val or hash_val == "N/A":
                return "NOT PROVIDED"
            if integrity_str == "MISMATCH":
                return "MISMATCH"
            elif integrity_str == "MATCH":
                return "MATCH"
            elif integrity_str in ("PRESERVED", "VERIFIED", "RECORDED"):
                return "RECORDED BASELINE"
            elif integrity_str == "NOT_CHECKED":
                return "NOT CHECKED"
            return "RECORDED BASELINE"

        hash_data = [
            [Paragraph("<b>Algorithm</b>", table_cell_bold), Paragraph("<b>Cryptographic Hash Fingerprint</b>", table_cell_bold), Paragraph("<b>Status / Baseline</b>", table_cell_bold)],
            [Paragraph("SHA-256", table_cell_bold), Paragraph(f"<font face='Courier' size='6.5'>{sha256_val or 'N/A'}</font>", table_cell), Paragraph(get_match_status(sha256_val), table_cell_bold)],
            [Paragraph("SHA-512", table_cell_bold), Paragraph(f"<font face='Courier' size='5.5'>{(sha512_val[:64] + '...') if sha512_val else 'NOT PROVIDED'}</font>", table_cell), Paragraph(get_match_status(sha512_val), table_cell)],
            [Paragraph("MD5", table_cell_bold), Paragraph(f"<font face='Courier' size='6.5'>{md5_val or 'NOT PROVIDED'}</font>", table_cell), Paragraph(get_match_status(md5_val), table_cell)],
        ]
        t_hash = Table(hash_data, colWidths=[65, 385, 90])
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
        story.append(Paragraph("2. Prototype Visual-Manipulation Indicator (Machine Learning Model)", section_style))
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
        waveform_path = raw_metrics.get("waveform_path")
        spectrogram_path = raw_metrics.get("spectrogram_path")
        video_frame_path = raw_metrics.get("video_frame_path")

        visual_exhibits = []
        if ela_path and os.path.exists(ela_path):
            visual_exhibits.append(("Exhibit A: Error Level Analysis (ELA 95% Heatmap)", ela_path))
        if fft_path and os.path.exists(fft_path):
            visual_exhibits.append(("Exhibit B: 2D FFT Frequency Power Spectrum", fft_path))
        if waveform_path and os.path.exists(waveform_path):
            visual_exhibits.append(("Exhibit C: Audio Waveform Amplitude Envelope", waveform_path))
        if spectrogram_path and os.path.exists(spectrogram_path):
            visual_exhibits.append(("Exhibit D: Audio STFT Spectrogram & Splicing Map", spectrogram_path))
        if video_frame_path and os.path.exists(video_frame_path):
            visual_exhibits.append(("Exhibit E: Decoded Video Keyframe Exhibit", video_frame_path))

        if visual_exhibits:
            story.append(Paragraph("5. Visual Forensic Exhibits", section_style))
            for title, img_p in visual_exhibits:
                try:
                    story.append(Paragraph(f"<b>{title}</b>", body_style))
                    story.append(Spacer(1, 1.5))
                    story.append(RLImage(img_p, width=220, height=110))
                    story.append(Spacer(1, 3))
                except Exception:
                    pass

        # 8. Application Custody Log (Workflow Documentation)
        story.append(Paragraph("6. Application Custody Log (Workflow Documentation)", section_style))
        story.append(Paragraph("<i>Note: Append-only application custody log stored in local SQLite database. Designed to support forensic workflow documentation; not an independent cryptographic proof or replacement for formal evidence-management procedures.</i>", ParagraphStyle('CocNote', parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 2))
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

        # 9. Legal Disclaimer
        disclaimer = (
            "<b>FORENSIC & LEGAL DISCLAIMER:</b> This report was generated automatically by the Truth Lens prototype "
            "(SIH PS-27) as an investigative review aid. Outputs, anomaly scores, and model predictions are automated screening "
            "indicators and do not constitute legal proof, certified expert testimony, or definitive determinations of authenticity "
            "or manipulation. All findings require independent examination by qualified forensic examiners and legal review prior to evidentiary submission."
        )
        story.append(Paragraph(disclaimer, ParagraphStyle('Disc', parent=styles['Normal'], fontSize=6.5, leading=8.5, textColor=colors.HexColor("#64748b"))))

        # Build PDF
        doc.build(story)
        return output_path

    @staticmethod
    def generate_case_summary_pdf(
        case_data: Dict[str, Any],
        summary_data: Dict[str, Any],
        evidence_items: List[Dict[str, Any]],
        custody_events: List[Dict[str, Any]]
    ) -> Path:
        case_id = case_data.get("case_id", "CASE-UNKNOWN")
        output_filename = f"truth_lens_case_report_{case_id}.pdf"
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
        
        # Styles
        title_style = ParagraphStyle(
            'CaseDocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER
        )
        subtitle_style = ParagraphStyle(
            'CaseDocSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#2563eb"),
            alignment=TA_CENTER
        )
        section_style = ParagraphStyle(
            'CaseDocSection',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=8,
            spaceAfter=4
        )
        table_cell = ParagraphStyle(
            'CaseTableCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#1e293b")
        )
        table_cell_bold = ParagraphStyle(
            'CaseTableCellBold',
            parent=table_cell,
            fontName='Helvetica-Bold'
        )

        story = []

        # 1. Header Banner
        story.append(Paragraph("TRUTH LENS : CASE FORENSIC INVESTIGATION SUMMARY", title_style))
        story.append(Paragraph("DIGITAL EVIDENCE CASE DOSSIER & MULTI-EXHIBIT AUDIT SUMMARY", subtitle_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"Truth Lens Case Report | Investigation Workspace (SIH PS-27) | Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            ParagraphStyle('MetaHead', parent=styles['Normal'], fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#64748b"))
        ))
        story.append(Spacer(1, 5))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=7))

        # 2. Case Metadata & Overview Table
        case_info_data = [
            [
                Paragraph("<b>Case Reference ID:</b>", table_cell),
                Paragraph(f"<b>{case_data.get('case_id', 'N/A')}</b>", table_cell_bold),
                Paragraph("<b>Investigation Status:</b>", table_cell),
                Paragraph(f"<font color='#2563eb'><b>{case_data.get('status', 'ACTIVE')}</b></font>", table_cell)
            ],
            [
                Paragraph("<b>Investigation Title:</b>", table_cell),
                Paragraph(case_data.get("title", "Untitled Case"), table_cell),
                Paragraph("<b>Lead Investigator:</b>", table_cell),
                Paragraph(case_data.get("lead_investigator", "N/A"), table_cell)
            ],
            [
                Paragraph("<b>Case Description:</b>", table_cell),
                Paragraph(case_data.get("description", "No description provided.") or "No description provided.", table_cell),
                Paragraph("<b>Case Created (UTC):</b>", table_cell),
                Paragraph(str(case_data.get("created_at", "N/A"))[:19], table_cell)
            ]
        ]
        t_case = Table(case_info_data, colWidths=[110, 160, 110, 160])
        t_case.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_case)
        story.append(Spacer(1, 8))

        # 3. Case KPI & Status Distribution Table
        story.append(Paragraph("Case Evidence Inventory & Risk Distribution", section_style))
        st_counts = summary_data.get("status_counts", {})
        rk_counts = summary_data.get("risk_counts", {})
        total_ev = summary_data.get("total_evidence", len(evidence_items))

        kpi_data = [
            [
                Paragraph("<b>Total Exhibits Ingested</b>", table_cell_bold),
                Paragraph("<b>Completed Analyses</b>", table_cell_bold),
                Paragraph("<b>Low Risk Baseline</b>", table_cell_bold),
                Paragraph("<b>Review Required</b>", table_cell_bold),
                Paragraph("<b>High Risk Flags</b>", table_cell_bold),
            ],
            [
                Paragraph(f"<b>{total_ev}</b>", table_cell),
                Paragraph(f"{st_counts.get('COMPLETED', 0)} / {total_ev}", table_cell),
                Paragraph(f"<font color='#16a34a'><b>{rk_counts.get('LOW RISK', 0)}</b></font>", table_cell),
                Paragraph(f"<font color='#ca8a04'><b>{rk_counts.get('REVIEW REQUIRED', 0)}</b></font>", table_cell),
                Paragraph(f"<font color='#dc2626'><b>{rk_counts.get('HIGH RISK', 0)}</b></font>", table_cell),
            ]
        ]
        t_kpi = Table(kpi_data, colWidths=[108, 108, 108, 108, 108])
        t_kpi.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor("#f8fafc")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_kpi)
        story.append(Spacer(1, 8))

        # 4. Evidence Exhibits Inventory Table
        story.append(Paragraph(f"Case Evidence Exhibits ({len(evidence_items)})", section_style))
        ev_table_data = [
            [
                Paragraph("<b>Evidence ID</b>", table_cell_bold),
                Paragraph("<b>Original Filename</b>", table_cell_bold),
                Paragraph("<b>Modality</b>", table_cell_bold),
                Paragraph("<b>Recorded SHA-256 Hash</b>", table_cell_bold),
                Paragraph("<b>Forensic Risk</b>", table_cell_bold),
                Paragraph("<b>Status</b>", table_cell_bold),
            ]
        ]
        if not evidence_items:
            ev_table_data.append([Paragraph("No evidence exhibits ingested in this case yet.", table_cell), Paragraph("", table_cell), Paragraph("", table_cell), Paragraph("", table_cell), Paragraph("", table_cell), Paragraph("", table_cell)])
        else:
            for item in evidence_items:
                r_cat = item.get("risk_category") or "PENDING"
                r_score = item.get("forensic_risk_score")
                if r_cat == "LOW RISK":
                    r_display = f"<font color='#16a34a'><b>LOW ({r_score:.1f}%)</b></font>" if r_score is not None else "<font color='#16a34a'><b>LOW RISK</b></font>"
                elif r_cat == "REVIEW REQUIRED":
                    r_display = f"<font color='#ca8a04'><b>REVIEW ({r_score:.1f}%)</b></font>" if r_score is not None else "<font color='#ca8a04'><b>REVIEW</b></font>"
                elif r_cat == "HIGH RISK":
                    r_display = f"<font color='#dc2626'><b>HIGH ({r_score:.1f}%)</b></font>" if r_score is not None else "<font color='#dc2626'><b>HIGH RISK</b></font>"
                else:
                    r_display = f"<font color='#64748b'>{r_cat}</font>"

                h_snippet = f"<font face='Courier' size='6'>{item.get('sha256_hash', '')[:16]}...</font>"
                ev_table_data.append([
                    Paragraph(f"<b>{item.get('evidence_id', '')}</b>", table_cell),
                    Paragraph(item.get("original_filename", "")[:28], table_cell),
                    Paragraph(item.get("modality", ""), table_cell),
                    Paragraph(h_snippet, table_cell),
                    Paragraph(r_display, table_cell),
                    Paragraph(item.get("status", ""), table_cell)
                ])

        t_ev = Table(ev_table_data, colWidths=[85, 125, 60, 110, 95, 65])
        t_ev.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_ev)
        story.append(Spacer(1, 8))

        # 5. Chronological Case Custody Timeline
        story.append(Paragraph(f"Case Custody Log & Audit Stream (Recent {min(len(custody_events), 25)} Events)", section_style))
        coc_table_data = [
            [
                Paragraph("<b>Timestamp (UTC)</b>", table_cell_bold),
                Paragraph("<b>Evidence ID</b>", table_cell_bold),
                Paragraph("<b>Action</b>", table_cell_bold),
                Paragraph("<b>Actor</b>", table_cell_bold),
                Paragraph("<b>Details</b>", table_cell_bold)
            ]
        ]
        if not custody_events:
            coc_table_data.append([Paragraph("No custody events recorded for this case.", table_cell), Paragraph("", table_cell), Paragraph("", table_cell), Paragraph("", table_cell), Paragraph("", table_cell)])
        else:
            for event in custody_events[:25]:
                coc_table_data.append([
                    Paragraph(str(event.get("timestamp", ""))[:19], table_cell),
                    Paragraph(event.get("evidence_id", ""), table_cell_bold),
                    Paragraph(event.get("action", ""), table_cell),
                    Paragraph(event.get("actor", ""), table_cell),
                    Paragraph(event.get("details", "")[:60] + ("..." if len(event.get("details", "")) > 60 else ""), table_cell)
                ])

        t_coc = Table(coc_table_data, colWidths=[90, 85, 110, 100, 155])
        t_coc.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0, 0), (-1, -1), 2.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t_coc)
        story.append(Spacer(1, 8))

        # 6. Legal Disclaimer
        disclaimer = (
            "<b>FORENSIC & LEGAL DISCLAIMER:</b> This case summary report was compiled automatically by the Truth Lens prototype "
            "(SIH PS-27) as an investigative workspace aid. Individual exhibit scores, physical signal metrics, and model outputs "
            "are automated screening indicators and do not constitute certified expert testimony or self-sufficient judicial proof. "
            "All findings require independent laboratory review, chain-of-custody corroboration, and legal evaluation prior to evidentiary submission."
        )
        story.append(Paragraph(disclaimer, ParagraphStyle('CaseDisc', parent=styles['Normal'], fontSize=6.5, leading=8.5, textColor=colors.HexColor("#64748b"))))

        doc.build(story)
        return output_path
