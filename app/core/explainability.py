import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.models.schemas import FindingSchema

class FindingBuilder:
    """
    Standardized constructor for explainable forensic findings.
    """
    @staticmethod
    def create_finding(
        evidence_id: str,
        signal_name: str,
        category: str,
        severity: str,
        score: float,
        explanation: str,
        location_ref: str = None
    ) -> Dict[str, Any]:
        return {
            "finding_id": f"FIND-{uuid.uuid4().hex[:8].upper()}",
            "evidence_id": evidence_id,
            "signal_name": signal_name,
            "category": category,
            "severity": severity.upper(),
            "score": round(float(score), 2),
            "explanation": explanation,
            "location_ref": location_ref,
            "created_at": datetime.utcnow().isoformat() + "Z"
        }

class ForensicCorrelationBuilder:
    """
    Constructs multi-signal 'WHY + WHERE + HOW' forensic correlation matrices.
    Links localized spatial patches with physical anomaly causes and judicial conclusions.
    """
    @staticmethod
    def build_correlation(
        evidence_id: str,
        forensic_taxonomy: str,
        risk_category: str,
        risk_score: float,
        findings: List[Dict[str, Any]],
        metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        localized_regions = metrics.get("localized_regions", [])

        # 1. WHERE: Spatial and container locations
        where_items = []
        for r in localized_regions:
            where_items.append({
                "region_id": r.get("region_id"),
                "label": r.get("semantic_label"),
                "anomaly_type": r.get("primary_anomaly"),
                "score": r.get("anomaly_score"),
                "bounding_box": r.get("bounding_box")
            })
        if not where_items:
            where_items.append({
                "region_id": "GLOBAL",
                "label": "Full Frame",
                "anomaly_type": "Uniform Distribution",
                "score": round(float(metrics.get("forensic_anomaly_score", 0.0)), 1)
            })

        # 2. WHAT: Observed physical and model anomalies
        what_items = []
        for f in findings:
            if f.get("severity") in ("CRITICAL", "HIGH", "MEDIUM"):
                what_items.append(f"{f.get('signal_name')}: {f.get('explanation')}")
        if not what_items:
            what_items.append("All physical signals (ELA compression, FFT spectrum, sensor noise) remain within normal baseline limits.")

        # 3. HOW: Inferred physical / digital mechanism
        if forensic_taxonomy == "LIKELY_AI_ASSISTED_MANIPULATION":
            how_mechanism = "Localized digital inpainting, generative fill, or synthetic object addition (e.g. eyewear, face edit) grafted onto an authentic photographic base."
        elif forensic_taxonomy == "LIKELY_AI_GENERATED":
            how_mechanism = "Full-frame synthetic generative diffusion/convolutional model execution, exhibiting periodic frequency grid artifacts and synthetic texture signatures."
        elif forensic_taxonomy == "LIKELY_TRADITIONAL_MANIPULATION":
            how_mechanism = "Digital post-processing, copy-move splicing, or container metadata alteration via desktop image editing software."
        elif forensic_taxonomy == "LIKELY_AUTHENTIC":
            how_mechanism = "Continuous optical sensor imaging pipeline characterized by consistent sensor noise distribution and uniform compression quantization."
        else:
            how_mechanism = "Inconclusive physical signal correlation due to conflicting indicators or insufficient metadata resolution."

        # 4. WHY: Forensic justification
        sig_count = sum(1 for f in findings if f.get("severity") in ("CRITICAL", "HIGH"))
        ensemble = metrics.get("ensemble_agreement") or {}
        consensus_txt = ensemble.get("consensus_label", "")
        conflict_txt = ensemble.get("conflict_description", "")

        if conflict_txt:
            why_conclusion = (
                f"Taxonomy marked as 'ANALYSIS INCONCLUSIVE' due to signal conflict: {conflict_txt} "
                f"(Evaluated {len(findings)} physical signals and {ensemble.get('total_specialists_evaluated', 0)} specialists)."
            )
        elif consensus_txt:
            why_conclusion = (
                f"Taxonomy categorized as '{forensic_taxonomy.replace('_', ' ')}' with {consensus_txt} "
                f"across {len(findings)} independent forensic signals (Forensic Anomaly Score: {metrics.get('forensic_anomaly_score', 0):.1f}/100, Composite Risk: {risk_score:.1f}/100)."
            )
        else:
            why_conclusion = (
                f"Taxonomy categorized as '{forensic_taxonomy.replace('_', ' ')}' based on correlation of {len(findings)} independent forensic signals "
                f"({sig_count} elevated indicators, Forensic Anomaly Score: {metrics.get('forensic_anomaly_score', 0):.1f}/100, Composite Risk: {risk_score:.1f}/100)."
            )

        return {
            "evidence_id": evidence_id,
            "forensic_taxonomy": forensic_taxonomy,
            "risk_category": risk_category,
            "risk_score": risk_score,
            "where_locations": where_items,
            "what_observations": what_items,
            "how_mechanism": how_mechanism,
            "why_conclusion": why_conclusion,
            "signal_agreement_count": sig_count,
            "ensemble_consensus": ensemble.get("consensus_verdict"),
            "agreement_percentage": ensemble.get("agreement_percentage")
        }
