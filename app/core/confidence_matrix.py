"""
Forensic Confidence Matrix
Builds a 6-axis multi-signal confidence grid from existing ensemble results.
No new ML calls — derives entirely from computed forensic_result and findings.
"""
from typing import Dict, Any, List, Optional


# Signal → colour mapping
_GREEN = "GREEN"    # Consistent with authentic
_RED = "RED"        # Consistent with manipulation
_AMBER = "AMBER"    # Inconclusive / unavailable
_GREY = "GREY"      # Not evaluated / not applicable


class ConfidenceMatrix:
    """
    Produces a structured, 6-axis Forensic Confidence Matrix from:
      - Ensemble agreement dict
      - Forensic risk score & taxonomy
      - Provenance status
      - Findings list
      - Metadata anomaly score
    
    Each axis returns: { label, authentic_signal, manipulated_signal, note }
    where signals are GREEN / RED / AMBER / GREY.
    """

    @staticmethod
    def build(
        forensic_risk_score: float,
        risk_category: str,
        forensic_taxonomy: str,
        ensemble_agreement: Optional[Dict[str, Any]],
        provenance_status: str,
        findings: List[Dict[str, Any]],
        raw_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        raw = raw_metrics or {}
        ens = ensemble_agreement or {}
        has_conflict = bool(ens.get("has_signal_conflict"))

        # -- AI MODELS AXIS --
        ai_indicator = raw.get("risk_components", {}).get("ai_manipulation_risk")
        model_status = raw.get("risk_components", {}).get("model_status", "")
        if model_status not in ("AVAILABLE",):
            ai_auth = _AMBER
            ai_manip = _AMBER
            ai_note = "Local ML model unavailable — no AI heuristic signal"
        elif ai_indicator is None:
            ai_auth = _AMBER
            ai_manip = _AMBER
            ai_note = "AI indicator not computed"
        elif ai_indicator <= 30.0:
            ai_auth = _GREEN
            ai_manip = _GREY
            ai_note = f"AI heuristic: {ai_indicator:.0f}/100 (authentic range)"
        elif ai_indicator >= 70.0:
            ai_auth = _GREY
            ai_manip = _RED
            ai_note = f"AI heuristic: {ai_indicator:.0f}/100 (manipulation range)"
        else:
            ai_auth = _AMBER
            ai_manip = _AMBER
            ai_note = f"AI heuristic: {ai_indicator:.0f}/100 (inconclusive range)"

        # -- PIXEL FORENSICS AXIS (ELA + FFT + PRNU) --
        forensic_anom = raw.get("forensic_anomaly_score", raw.get("signal_anomalies_score", 0.0))
        try:
            forensic_anom = float(forensic_anom)
        except Exception:
            forensic_anom = 0.0

        if forensic_anom <= 30.0:
            pix_auth = _GREEN
            pix_manip = _GREY
            pix_note = f"Pixel anomaly score {forensic_anom:.0f}/100 (within normal limits)"
        elif forensic_anom >= 65.0:
            pix_auth = _GREY
            pix_manip = _RED
            pix_note = f"Pixel anomaly score {forensic_anom:.0f}/100 (elevated anomaly)"
        else:
            pix_auth = _AMBER
            pix_manip = _AMBER
            pix_note = f"Pixel anomaly score {forensic_anom:.0f}/100 (moderate — review)"

        # -- METADATA AXIS --
        meta_risk = raw.get("risk_components", {}).get("metadata_risk", 0.0)
        try:
            meta_risk = float(meta_risk)
        except Exception:
            meta_risk = 0.0

        meta_findings = [f for f in findings if f.get("category") in ("METADATA", "PROVENANCE")]
        has_software_tag = any(
            "software" in f.get("signal_name", "").lower() or
            "editing" in f.get("signal_name", "").lower() or
            "photoshop" in f.get("explanation", "").lower()
            for f in meta_findings
        )
        if meta_risk <= 20.0 and not has_software_tag:
            meta_auth = _GREEN
            meta_manip = _GREY
            meta_note = "No editing suite markers; EXIF consistent with capture device"
        elif has_software_tag or meta_risk >= 50.0:
            meta_auth = _AMBER
            meta_manip = _RED
            meta_note = "Post-processing software or EXIF anomaly detected"
        else:
            meta_auth = _AMBER
            meta_manip = _AMBER
            meta_note = "Metadata partially consistent — review recommended"

        # -- PROVENANCE AXIS --
        ps = provenance_status.upper() if provenance_status else "NOT_AVAILABLE"
        if ps == "VERIFIED":
            prov_auth = _GREEN
            prov_manip = _GREY
            prov_note = "C2PA content credential verified"
        elif "DETECTED" in ps and "UNVERIFIED" in ps:
            prov_auth = _AMBER
            prov_manip = _AMBER
            prov_note = "C2PA manifest marker detected but not cryptographically verified"
        elif ps == "INVALID":
            prov_auth = _GREY
            prov_manip = _RED
            prov_note = "C2PA manifest invalid or tampered"
        elif ps == "NOT_VERIFIED":
            prov_auth = _AMBER
            prov_manip = _AMBER
            prov_note = "No verifiable content credential found"
        else:
            prov_auth = _GREY
            prov_manip = _GREY
            prov_note = "C2PA provenance unavailable — cannot assess"

        # -- REGION ANALYSIS AXIS --
        localized_regions = raw.get("localized_regions", [])
        localized_findings = [f for f in findings if f.get("category") == "LOCALIZED_MANIPULATION"]
        if localized_findings:
            sev = localized_findings[0].get("severity", "INFO")
            if sev in ("CRITICAL", "HIGH"):
                reg_auth = _GREY
                reg_manip = _RED
                region_label = localized_findings[0].get("location_ref", "Localized region")
                reg_note = f"Localized manipulation region flagged: {region_label}"
            else:
                reg_auth = _AMBER
                reg_manip = _AMBER
                reg_note = "Moderate localized anomaly — review recommended"
        elif localized_regions:
            reg_auth = _AMBER
            reg_manip = _AMBER
            reg_note = f"{len(localized_regions)} suspicious region(s) identified by patch localizer"
        else:
            reg_auth = _GREEN
            reg_manip = _GREY
            reg_note = "No localized anomalous regions detected across sliding ROI grid"

        # -- SIGNAL AGREEMENT AXIS --
        total_specialists = ens.get("total_specialists_evaluated", 0)
        manipulated_count = ens.get("manipulated_count", 0)
        authentic_count = ens.get("authentic_count", 0)
        agreement_pct = ens.get("agreement_percentage", 0.0)
        consensus_verdict = ens.get("consensus_verdict", "INSUFFICIENT_SPECIALISTS")

        if has_conflict:
            agree_auth = _AMBER
            agree_manip = _AMBER
            agree_note = f"⚠ Conflicting forensic signals — {total_specialists} specialists evaluated"
        elif total_specialists == 0:
            agree_auth = _GREY
            agree_manip = _GREY
            agree_note = "No specialist ensemble data available"
        elif consensus_verdict in ("STRONG_MANIPULATION_CONSENSUS", "MAJORITY_MANIPULATION"):
            agree_auth = _GREY
            agree_manip = _RED
            agree_note = f"{manipulated_count}/{total_specialists} specialists indicate manipulation ({agreement_pct:.0f}% agreement)"
        elif consensus_verdict in ("AUTHENTIC_BASELINE_CONSENSUS", "MAJORITY_AUTHENTIC"):
            agree_auth = _GREEN
            agree_manip = _GREY
            agree_note = f"{authentic_count}/{total_specialists} specialists indicate authentic ({agreement_pct:.0f}% agreement)"
        else:
            agree_auth = _AMBER
            agree_manip = _AMBER
            agree_note = f"{total_specialists} specialists — inconclusive consensus ({agreement_pct:.0f}% agreement)"

        # --- Overall summary ---
        red_count = sum(1 for s in [
            ai_manip, pix_manip, meta_manip, prov_manip, reg_manip, agree_manip
        ] if s == _RED)
        green_count = sum(1 for s in [
            ai_auth, pix_auth, meta_auth, prov_auth, reg_auth, agree_auth
        ] if s == _GREEN)

        return {
            "axes": [
                {
                    "label": "AI Models",
                    "icon": "🤖",
                    "authentic_signal": ai_auth,
                    "manipulated_signal": ai_manip,
                    "note": ai_note
                },
                {
                    "label": "Pixel Forensics",
                    "icon": "🔬",
                    "authentic_signal": pix_auth,
                    "manipulated_signal": pix_manip,
                    "note": pix_note
                },
                {
                    "label": "Metadata",
                    "icon": "🗂️",
                    "authentic_signal": meta_auth,
                    "manipulated_signal": meta_manip,
                    "note": meta_note
                },
                {
                    "label": "Provenance",
                    "icon": "🔐",
                    "authentic_signal": prov_auth,
                    "manipulated_signal": prov_manip,
                    "note": prov_note
                },
                {
                    "label": "Region Analysis",
                    "icon": "📍",
                    "authentic_signal": reg_auth,
                    "manipulated_signal": reg_manip,
                    "note": reg_note
                },
                {
                    "label": "Signal Agreement",
                    "icon": "⚖️",
                    "authentic_signal": agree_auth,
                    "manipulated_signal": agree_manip,
                    "note": agree_note
                }
            ],
            "summary": {
                "manipulation_signals": red_count,
                "authentic_signals": green_count,
                "total_axes": 6,
                "has_conflict": has_conflict,
                "overall_verdict": risk_category,
                "forensic_taxonomy": forensic_taxonomy
            }
        }
