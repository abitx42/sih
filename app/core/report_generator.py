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
        raw_metrics = forensic_result.get("raw_metrics_json", {})
        if isinstance(raw_metrics, str):
            try:
                raw_metrics = json.loads(raw_metrics)
            except Exception:
                raw_metrics = {}

        forensic_taxonomy = raw_metrics.get("forensic_taxonomy", forensic_result.get("forensic_taxonomy", "ANALYSIS_INCONCLUSIVE")).replace("_", " ")

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
                Paragraph("<b>Forensic Taxonomy:</b>", bold_body), Paragraph(f"<b>{forensic_taxonomy}</b>", ParagraphStyle('TaxStyle', parent=body_style, textColor=colors.HexColor("#2563eb"), fontName='Helvetica-Bold')),
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

        # 4. Multi-Specialist Forensic AI Ensemble & Consensus Assessment
        story.append(Paragraph("2. Multi-Specialist Forensic AI Ensemble & Consensus Assessment", section_style))
        ensemble_data = raw_metrics.get("ensemble_agreement", {})
        specialists_list = ensemble_data.get("specialist_breakdown", [])

        if specialists_list:
            ens_table_data = [
                [
                    Paragraph("<b>Forensic Specialist / Module</b>", table_cell_bold),
                    Paragraph("<b>Focus & Scope</b>", table_cell_bold),
                    Paragraph("<b>Verdict</b>", table_cell_bold),
                    Paragraph("<b>Indicator / Score</b>", table_cell_bold),
                    Paragraph("<b>Status & Notes</b>", table_cell_bold)
                ]
            ]
            for s in specialists_list:
                v = s.get("verdict", "N/A")
                if v == "MANIPULATED":
                    v_color = "#dc2626"
                elif v == "AUTHENTIC":
                    v_color = "#16a34a"
                elif v == "SKIPPED":
                    v_color = "#64748b"
                else:
                    v_color = "#ca8a04"

                ind_val = s.get("indicator")
                ind_str = f"{ind_val * 100:.1f}%" if ind_val is not None else (f"{s.get('score', 0):.1f}/100" if "score" in s else s.get("provenance_status", "N/A"))

                ens_table_data.append([
                    Paragraph(f"<b>{s.get('name', 'Specialist')}</b>", table_cell),
                    Paragraph(s.get("focus", ""), table_cell),
                    Paragraph(f"<font color='{v_color}'><b>{v}</b></font>", table_cell),
                    Paragraph(str(ind_str), table_cell),
                    Paragraph(s.get("details", ""), table_cell)
                ])

            t_ens = Table(ens_table_data, colWidths=[130, 125, 75, 70, 140])
            t_ens.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_ens)
            story.append(Spacer(1, 2))

            consensus_lbl = ensemble_data.get("consensus_label", "Consensus Evaluated")
            story.append(Paragraph(f"<b>Specialist Consensus:</b> {consensus_lbl} | Agreement Ratio: {ensemble_data.get('agreement_percentage', 0):.1f}%", ParagraphStyle('ConsensusHead', parent=body_style, fontName='Helvetica-Bold', textColor=colors.HexColor("#2563eb"))))
            if ensemble_data.get("has_signal_conflict"):
                story.append(Paragraph(f"<b>⚠️ Signal Conflict Note:</b> {ensemble_data.get('conflict_description')}", ParagraphStyle('ConflictHead', parent=body_style, fontName='Helvetica-Bold', textColor=colors.HexColor("#d97706"))))
        else:
            ml_model = forensic_result.get("ai_model_name", "dima806/deepfake_vs_real_image_detection")
            ml_status = forensic_result.get("model_status", "AVAILABLE")
            ml_indicator = forensic_result.get("ai_manipulation_indicator")
            indicator_str = f"{round(ml_indicator * 100, 1)}%" if ml_indicator is not None else ml_status
            ml_table_data = [
                [
                    Paragraph("<b>Model Architecture</b>", table_cell_bold),
                    Paragraph("<b>Status</b>", table_cell_bold),
                    Paragraph("<b>AI Indicator</b>", table_cell_bold)
                ],
                [
                    Paragraph(ml_model, table_cell),
                    Paragraph(ml_status, table_cell_bold),
                    Paragraph(indicator_str, table_cell_bold)
                ]
            ]
            t_ml = Table(ml_table_data, colWidths=[240, 150, 150])
            t_ml.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_ml)

        story.append(Spacer(1, 6))

        # 5. Multi-Signal "Why + Where + How" Evidence Correlation
        corr = raw_metrics.get("correlation_summary", {})
        if corr:
            story.append(Paragraph("3. Multi-Signal 'Why + Where + How' Evidence Correlation", section_style))
            where_locs = corr.get("where_locations", [])
            where_desc = ", ".join([f"{loc.get('label', 'ROI')} ({loc.get('anomaly_type', 'Anomaly')})" for loc in where_locs])
            
            corr_table_data = [
                [Paragraph("<b>WHERE (Spatial ROI)</b>", table_cell_bold), Paragraph(where_desc or "Global Frame", table_cell)],
                [Paragraph("<b>HOW (Physical Inferred Mechanism)</b>", table_cell_bold), Paragraph(corr.get("how_mechanism", "N/A"), table_cell)],
                [Paragraph("<b>WHY (Forensic Conclusion)</b>", table_cell_bold), Paragraph(corr.get("why_conclusion", "N/A"), table_cell)]
            ]
            t_corr = Table(corr_table_data, colWidths=[140, 400])
            t_corr.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(t_corr)
            story.append(Spacer(1, 6))

        # 6. Executive Forensic Narrative & Recommendations
        story.append(Paragraph("4. Executive Forensic Narrative & Recommendations", section_style))
        summary_text = forensic_result.get("summary_narrative") or "Automated multi-signal forensic evaluation completed."
        recom_text = forensic_result.get("recommendations") or "No further actions required."
        
        story.append(Paragraph(f"<b>Automated Findings Synthesis:</b> {summary_text}", body_style))
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"<b>Investigator Recommendations:</b><br/>{recom_text.replace(chr(10), '<br/>')}", body_style))
        story.append(Spacer(1, 6))

        # 7. Detailed Forensic Findings Breakdown
        story.append(Paragraph("5. Technical Forensic Findings Breakdown", section_style))
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

        # 8. Visual Forensic Exhibits
        heatmap_path = raw_metrics.get("manipulation_heatmap_path")
        ela_path = raw_metrics.get("ela_image_path")
        fft_path = raw_metrics.get("fft_image_path")
        waveform_path = raw_metrics.get("waveform_path")
        spectrogram_path = raw_metrics.get("spectrogram_path")
        video_frame_path = raw_metrics.get("video_frame_path")

        visual_exhibits = []
        if heatmap_path and os.path.exists(heatmap_path):
            visual_exhibits.append(("Exhibit A: Spatial Patch Manipulation Heatmap (Localized Anomaly Map)", heatmap_path))
        if ela_path and os.path.exists(ela_path):
            visual_exhibits.append(("Exhibit B: Error Level Analysis (ELA 95% Heatmap)", ela_path))
        if fft_path and os.path.exists(fft_path):
            visual_exhibits.append(("Exhibit C: 2D FFT Frequency Power Spectrum", fft_path))
        if waveform_path and os.path.exists(waveform_path):
            visual_exhibits.append(("Exhibit D: Audio Waveform Amplitude Envelope", waveform_path))
        if spectrogram_path and os.path.exists(spectrogram_path):
            visual_exhibits.append(("Exhibit E: Audio STFT Spectrogram & Splicing Map", spectrogram_path))
        if video_frame_path and os.path.exists(video_frame_path):
            visual_exhibits.append(("Exhibit F: Decoded Video Keyframe Exhibit", video_frame_path))

        # 5. Localized Alteration Analysis
        loc_data = raw_metrics.get("localization") or {}
        policy_out = raw_metrics.get("policy_outcome") or {}
        if loc_data or policy_out:
            story.append(Paragraph("5. Localized Alteration Analysis", section_style))
            
            # Policy Outcome Banner
            p_label = policy_out.get("label", "Inconclusive")
            p_desc = policy_out.get("description", "")
            p_trigger = policy_out.get("trigger", "")
            
            story.append(Paragraph(f"<b>Policy Decision Outcome:</b> <font color='#2563eb'><b>{p_label}</b></font> <font color='#64748b' size='7'>[CALIBRATION: UNVALIDATED]</font>", body_style))
            if p_desc:
                story.append(Paragraph(f"<i>{p_desc}</i>", ParagraphStyle('PolDesc', parent=body_style, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#475569"))))
            if p_trigger:
                story.append(Paragraph(f"<b>Rule Trigger:</b> <font size='7' color='#64748b'>{p_trigger}</font>", body_style))
            story.append(Spacer(1, 3))

            # Regions Table
            regions = loc_data.get("localized_regions", [])
            if regions:
                story.append(Paragraph("<b>Bounded Anomaly Regions (Statistical Concentration):</b>", body_style))
                loc_table_data = [
                    [
                        Paragraph("<b>Region ID</b>", table_cell_bold),
                        Paragraph("<b>Area %</b>", table_cell_bold),
                        Paragraph("<b>Evidence Strength</b>", table_cell_bold),
                        Paragraph("<b>Signal Agreement</b>", table_cell_bold),
                        Paragraph("<b>Neutral Location & Description</b>", table_cell_bold),
                    ]
                ]
                for r in regions:
                    str_val = r.get("evidence_strength", "MODERATE")
                    s_color = "#dc2626" if str_val == "HIGH" else ("#d97706" if str_val == "MODERATE" else "#16a34a")
                    loc_table_data.append([
                        Paragraph(f"<b>{r.get('region_id', 'ROI')}</b>", table_cell),
                        Paragraph(f"{r.get('affected_area_pct', 0.0)}%", table_cell),
                        Paragraph(f"<font color='{s_color}'><b>{str_val}</b></font>", table_cell),
                        Paragraph(str(r.get("signal_agreement", "Heuristic")), table_cell),
                        Paragraph(r.get("neutral_description", "Statistical anomaly concentration; method undetermined."), table_cell),
                    ])
                t_loc = Table(loc_table_data, colWidths=[60, 40, 75, 75, 290])
                t_loc.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ]))
                story.append(t_loc)
                story.append(Spacer(1, 3))
            elif loc_data.get("localization_status") == "AVAILABLE":
                story.append(Paragraph("<i>No distinct localized anomaly clusters detected above threshold (uniform spatial distribution).</i>", body_style))
                story.append(Spacer(1, 3))
            else:
                story.append(Paragraph(f"<i>Localization status: {loc_data.get('localization_status', 'UNAVAILABLE')}. {loc_data.get('error_detail', '')}</i>", body_style))
                story.append(Spacer(1, 3))

            # Limitation notice
            story.append(Paragraph(
                "<b>LIMITATION:</b> <i>Image-only analysis is probabilistic and UNVALIDATED. Statistical anomaly concentrations do not constitute pixel-level proof of manipulation, nor do they determine editing tool or AI usage. Findings require qualified investigator review.</i>",
                ParagraphStyle('LocLimit', parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#b45309"))
            ))
            story.append(Spacer(1, 6))


        # 6. Application Custody Log (Workflow Documentation)
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

        # 9. Forensic Confidence Matrix
        story.append(Paragraph("7. Forensic Confidence Matrix", section_style))
        story.append(Paragraph(
            "<i>6-axis multi-signal evaluation grid. Derived from all collected forensic signals — no new computation performed for this section.</i>",
            ParagraphStyle('MatrixNote', parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))
        ))
        story.append(Spacer(1, 3))

        manipulation_subtype = forensic_result.get("manipulation_subtype", raw_metrics.get("risk_components", {}).get("manipulation_subtype", ""))
        if manipulation_subtype:
            story.append(Paragraph(f"<b>Manipulation Sub-type Classification:</b> {manipulation_subtype.replace('_', ' ')}", body_style))
            story.append(Spacer(1, 3))

        try:
            from app.core.confidence_matrix import ConfidenceMatrix
            ensemble_agreement_json = forensic_result.get("ensemble_agreement_json") or "{}"
            import json as _json
            ensemble_agg = _json.loads(ensemble_agreement_json) if isinstance(ensemble_agreement_json, str) else ensemble_agreement_json
            forensic_tax = raw_metrics.get("forensic_taxonomy") or raw_metrics.get("risk_components", {}).get("forensic_taxonomy", "ANALYSIS_INCONCLUSIVE")

            matrix = ConfidenceMatrix.build(
                forensic_risk_score=forensic_result.get("forensic_risk_score", 0.0),
                risk_category=forensic_result.get("risk_category", "REVIEW REQUIRED"),
                forensic_taxonomy=forensic_tax,
                ensemble_agreement=ensemble_agg,
                provenance_status=forensic_result.get("provenance_status", "NOT_AVAILABLE"),
                findings=[dict(f) for f in findings],
                raw_metrics=raw_metrics
            )
            _sig_map = {"GREEN": ("#16a34a", "✓"), "RED": ("#dc2626", "✗"), "AMBER": ("#ca8a04", "~"), "GREY": ("#94a3b8", "—")}

            matrix_table_data = [
                [
                    Paragraph("<b>Signal Axis</b>", table_cell_bold),
                    Paragraph("<b>→ Baseline</b>", table_cell_bold),
                    Paragraph("<b>→ Alteration Flagged</b>", table_cell_bold),
                    Paragraph("<b>Note (Unvalidated)</b>", table_cell_bold),
                ]
            ]
            for axis in matrix["axes"]:
                a_col, a_sym = _sig_map.get(axis["authentic_signal"], ("#94a3b8", "—"))
                m_col, m_sym = _sig_map.get(axis["manipulated_signal"], ("#94a3b8", "—"))
                matrix_table_data.append([
                    Paragraph(f"<b>{axis.get('icon', '')} {axis['label']}</b>", table_cell),
                    Paragraph(f"<font color='{a_col}'><b>{a_sym}</b></font>", table_cell),
                    Paragraph(f"<font color='{m_col}'><b>{m_sym}</b></font>", table_cell),
                    Paragraph(axis.get("note", ""), table_cell),
                ])
            t_matrix = Table(matrix_table_data, colWidths=[110, 65, 85, 280])

            t_matrix.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
            ]))
            story.append(t_matrix)
            summary = matrix.get("summary", {})
            story.append(Spacer(1, 2))
            story.append(Paragraph(
                f"<b>Signal Agreement:</b> {summary.get('manipulation_signals', 0)} of {summary.get('total_axes', 6)} axes indicate manipulation; {summary.get('authentic_signals', 0)} indicate authentic.",
                body_style
            ))
        except Exception as _mx_err:
            story.append(Paragraph(f"Confidence matrix unavailable: {type(_mx_err).__name__}", body_style))
        story.append(Spacer(1, 8))

        # 10. Investigator Review
        investigator_review = None
        try:
            from app.database import get_db as _get_db
            with _get_db() as _conn:
                _cr = _conn.cursor()
                _cr.execute("SELECT * FROM investigator_reviews WHERE evidence_id = ? ORDER BY submitted_at DESC LIMIT 1", (evidence_data.get("evidence_id", ""),))
                _rev = _cr.fetchone()
                if _rev:
                    investigator_review = dict(_rev)
        except Exception:
            pass

        story.append(Paragraph("8. Investigator Assessment", section_style))
        if investigator_review:
            v = investigator_review.get("verdict", "")
            verdict_colors = {"AGREE": "#16a34a", "DISAGREE": "#dc2626", "NEEDS_FURTHER_EXAMINATION": "#ca8a04"}
            v_col = verdict_colors.get(v, "#64748b")
            story.append(Paragraph(f"<b>Verdict:</b> <font color='{v_col}'><b>{v.replace('_', ' ')}</b></font>", body_style))
            story.append(Paragraph(f"<b>Reviewed by:</b> {investigator_review.get('reviewer_name', 'N/A')} on {str(investigator_review.get('submitted_at', ''))[:19]} UTC", body_style))
            if investigator_review.get("notes"):
                story.append(Paragraph(f"<b>Notes:</b> {investigator_review.get('notes')}", body_style))
        else:
            story.append(Paragraph("No investigator review has been submitted for this exhibit.", ParagraphStyle('NoRev', parent=body_style, textColor=colors.HexColor("#64748b"))))
        story.append(Spacer(1, 8))

        # 11. Reproducibility Record
        repro_json = forensic_result.get("reproducibility_json")
        if repro_json:
            try:
                import json as _json
                repro = _json.loads(repro_json) if isinstance(repro_json, str) else repro_json
                story.append(Paragraph("9. Reproducibility Record", section_style))
                story.append(Paragraph(
                    "<i>This record enables analysis reproducibility. Re-running with the same TruthLens version, model checkpoint, and input SHA-256 should yield equivalent findings.</i>",
                    ParagraphStyle('ReproNote', parent=body_style, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))
                ))
                story.append(Spacer(1, 2))
                repro_rows = [
                    ["Platform", repro.get("platform", "Truth Lens")],
                    ["TruthLens Version", repro.get("truthlens_version", "N/A")],
                    ["Analysis Mode", repro.get("analysis_mode", "N/A")],
                    ["AI Model", f"{repro.get('ai_model_name', 'N/A')} v{repro.get('ai_model_version', 'N/A')}"],
                    ["Model Checkpoint", repro.get("ai_model_checkpoint", "N/A")],
                    ["Specialist Count", str(repro.get("specialist_ensemble_count", "N/A"))],
                    ["Input SHA-256", repro.get("input_sha256", "N/A")[:32] + "..."],
                    ["Analysis Timestamp (UTC)", str(repro.get("analysis_timestamp_utc", "N/A"))[:19]],
                ]
                repro_table = [[Paragraph(f"<b>{r[0]}</b>", table_cell), Paragraph(str(r[1]), table_cell)] for r in repro_rows]
                t_repro = Table(repro_table, colWidths=[150, 390])
                t_repro.setStyle(TableStyle([
                    ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ]))
                story.append(t_repro)
                story.append(Spacer(1, 8))
            except Exception:
                pass

        # 11. Visual Forensic Exhibits & Heatmaps
        if visual_exhibits:
            try:
                from reportlab.platypus import Image as RLImage
                story.append(Paragraph("10. Visual Forensic Exhibits & Heatmaps", section_style))
                for ex_title, ex_path in visual_exhibits[:4]:
                    story.append(Paragraph(f"<b>{ex_title}</b>", body_style))
                    try:
                        rl_img = RLImage(ex_path, width=480, height=180)
                        story.append(rl_img)
                        story.append(Spacer(1, 4))
                    except Exception:
                        pass
                story.append(Spacer(1, 6))
            except Exception:
                pass

        # 12. Legal Disclaimer
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
