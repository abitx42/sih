import io
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import pytest

from app.analyzers.patch_localizer import PatchLocalizer
from app.core.risk_engine import RiskEngine
from app.core.explainability import ForensicCorrelationBuilder

def test_patch_localizer_uniform_image():
    # 1. Create a uniform synthetic image with natural random sensor noise
    np.random.seed(42)
    base_arr = np.ones((256, 256, 3), dtype=np.uint8) * 128
    noise = np.random.normal(0, 4, (256, 256, 3)).astype(np.int16)
    noisy_img_arr = np.clip(base_arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(noisy_img_arr)

    localizer = PatchLocalizer(target_patch_size=64)
    res = localizer.analyze_patches(img, ela_img=None, evidence_id="TEST-UNIFORM-001")

    assert res["max_patch_anomaly"] < 45.0
    assert len(res["localized_regions"]) == 0
    assert res["patch_count"] > 0
    if res["heatmap_path"]:
        assert Path(res["heatmap_path"]).exists()

def test_patch_localizer_injected_sunglasses_patch():
    # 2. Create base image (natural gradient + uniform sensor noise)
    np.random.seed(42)
    h, w = 300, 300
    y, x = np.mgrid[0:h, 0:w]
    grad = ((y / h) * 100 + 50).astype(np.uint8)
    base_arr = np.stack([grad, grad, grad], axis=-1)
    noise = np.random.normal(0, 3, (h, w, 3)).astype(np.int16)
    img_arr = np.clip(base_arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(img_arr)

    # Inject simulated "sunglasses" / inpainting patch (y: 80-140, x: 90-210)
    # Different frequency noise and strong sharp boundaries
    draw = ImageDraw.Draw(img)
    draw.rectangle([90, 80, 210, 140], fill=(20, 20, 30), outline=(220, 220, 220), width=3)

    localizer = PatchLocalizer(target_patch_size=48)
    res = localizer.analyze_patches(img, ela_img=None, evidence_id="TEST-SUNGLASSES-001")

    assert res["max_patch_anomaly"] >= 50.0
    assert len(res["localized_regions"]) >= 1
    roi = res["localized_regions"][0]
    assert roi["anomaly_score"] >= 50.0
    bbox = roi["bounding_box"]
    assert "Eyewear / Facial" in roi["semantic_label"] or "Upper" in roi["semantic_label"] or "Central" in roi["semantic_label"]
    assert bbox["ymin"] <= 0.60
    assert Path(res["heatmap_path"]).exists()

def test_forensic_taxonomy_evaluation_scenarios():
    # 1. Uniform Authentic Scenario
    tax_auth = RiskEngine.evaluate_taxonomy(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.08,
        model_status="AVAILABLE",
        forensic_anomaly_score=15.0,
        metadata_anomaly_score=5.0,
        provenance_status="NOT_AVAILABLE",
        findings=[],
        final_risk_score=18.0
    )
    assert tax_auth == "LIKELY_AUTHENTIC"

    # 2. Localized AI-Assisted Manipulation (Sunglasses / Face swap)
    localized_finding = {
        "finding_id": "F-01",
        "category": "LOCALIZED_MANIPULATION",
        "severity": "CRITICAL",
        "score": 88.0,
        "signal_name": "Localized Manipulation Detected (Eyewear / Facial Region)",
        "explanation": "Sensor noise variance discrepancy detected in eyewear region."
    }
    tax_local = RiskEngine.evaluate_taxonomy(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.48,  # Moderate / ambiguous global ML
        model_status="AVAILABLE",
        forensic_anomaly_score=68.0,
        metadata_anomaly_score=10.0,
        provenance_status="NOT_AVAILABLE",
        findings=[localized_finding],
        final_risk_score=78.0
    )
    assert tax_local == "LIKELY_AI_ASSISTED_MANIPULATION"

    # 3. Whole-Image Generative Synthesis
    ai_finding = {
        "finding_id": "F-02",
        "category": "AI_DETECTION",
        "severity": "CRITICAL",
        "score": 96.0,
        "signal_name": "ML Vision Classifier Flag (ViT)",
        "explanation": "Global synthetic textures."
    }
    tax_gen = RiskEngine.evaluate_taxonomy(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.92,
        model_status="AVAILABLE",
        forensic_anomaly_score=58.0,
        metadata_anomaly_score=15.0,
        provenance_status="NOT_AVAILABLE",
        findings=[ai_finding],
        final_risk_score=85.0
    )
    assert tax_gen == "LIKELY_AI_GENERATED"

    # 4. Traditional Photoshop Splicing
    splice_finding = {
        "finding_id": "F-03",
        "category": "SIGNAL_ANALYSIS",
        "severity": "HIGH",
        "score": 75.0,
        "signal_name": "High Error Level Discrepancy",
        "explanation": "Double compression."
    }
    tax_trad = RiskEngine.evaluate_taxonomy(
        integrity_status="VERIFIED",
        ai_manipulation_indicator=0.10,
        model_status="AVAILABLE",
        forensic_anomaly_score=62.0,
        metadata_anomaly_score=60.0,
        provenance_status="NOT_AVAILABLE",
        findings=[splice_finding],
        final_risk_score=68.0
    )
    assert tax_trad == "LIKELY_TRADITIONAL_MANIPULATION"

def test_why_where_how_correlation_builder():
    findings = [
        {
            "signal_name": "Localized Manipulation Detected (Eyewear Region)",
            "severity": "HIGH",
            "explanation": "Noise residual mismatch in eyewear bounding box."
        }
    ]
    metrics = {
        "forensic_anomaly_score": 72.0,
        "localized_regions": [
            {
                "region_id": "ROI-1",
                "semantic_label": "Eyewear / Facial Region",
                "primary_anomaly": "Sensor Noise Inconsistency",
                "anomaly_score": 84.0,
                "bounding_box": {"ymin": 0.25, "xmin": 0.30, "ymax": 0.45, "xmax": 0.70}
            }
        ]
    }
    corr = ForensicCorrelationBuilder.build_correlation(
        evidence_id="EV-TEST-CORR",
        forensic_taxonomy="LIKELY_AI_ASSISTED_MANIPULATION",
        risk_category="HIGH RISK",
        risk_score=78.5,
        findings=findings,
        metrics=metrics
    )

    assert corr["evidence_id"] == "EV-TEST-CORR"
    assert corr["forensic_taxonomy"] == "LIKELY_AI_ASSISTED_MANIPULATION"
    assert len(corr["where_locations"]) == 1
    assert "Eyewear" in corr["where_locations"][0]["label"]
    assert "inpainting" in corr["how_mechanism"].lower()
    assert corr["signal_agreement_count"] >= 1
