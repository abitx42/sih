"""
tests/test_reference_workspace.py
Tests for Phase 3: Match Analysis, Fine-Grained Region Segmentation, and Auto-Comparison.
"""
import io
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app
from app.core.reference_comparator import ReferenceComparator, STATUS_CONFIRMED

client = TestClient(app)


def _create_image_pair() -> tuple[bytes, bytes]:
    # Original image
    img1 = Image.new("RGB", (300, 300), color=(100, 150, 200))
    d1 = ImageDraw.Draw(img1)
    d1.rectangle([50, 50, 250, 250], fill=(200, 100, 50))
    buf1 = io.BytesIO()
    img1.save(buf1, format="JPEG")

    # Modified / Inpainted image
    img2 = Image.new("RGB", (300, 300), color=(100, 150, 200))
    d2 = ImageDraw.Draw(img2)
    d2.rectangle([50, 50, 250, 250], fill=(200, 100, 50))
    # Alter top-right quadrant
    d2.ellipse([160, 50, 250, 140], fill=(255, 255, 255))
    buf2 = io.BytesIO()
    img2.save(buf2, format="JPEG")

    return buf1.getvalue(), buf2.getvalue()


def test_fine_grained_region_segmentation(tmp_path):
    """Verify ReferenceComparator segments altered zones and assigns categories."""
    orig_bytes, mod_bytes = _create_image_pair()
    p1 = tmp_path / "orig.jpg"
    p2 = tmp_path / "mod.jpg"
    p1.write_bytes(orig_bytes)
    p2.write_bytes(mod_bytes)

    res = ReferenceComparator.compare(
        evidence_path=p2,
        reference_path=p1,
        evidence_id="EV-TEST-REF-01"
    )

    assert res["comparison_status"] == STATUS_CONFIRMED
    assert res["alignment_succeeded"] is True
    assert res["changed_region_count"] >= 1
    assert "authentic_percentage" in res
    assert "altered_percentage" in res
    assert res["altered_percentage"] > 0
    assert len(res["changed_regions"]) > 0

    first_reg = res["changed_regions"][0]
    assert "region_id" in first_reg
    assert "category" in first_reg
    assert "bbox_norm" in first_reg


def test_auto_compare_endpoint():
    """Verify /api/evidence/{id}/auto-compare-web endpoint execution."""
    orig_bytes, mod_bytes = _create_image_pair()
    files = {"file": ("demo_spliced_match.jpg", mod_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}
    upload_res = client.post("/api/evidence/upload", data=data, files=files)
    assert upload_res.status_code in (200, 202)
    ev_id = upload_res.json()["evidence_id"]

    # Trigger auto-compare
    comp_res = client.post(f"/api/evidence/{ev_id}/auto-compare-web", json={
        "match_title": "Original News Agency Photo"
    })
    assert comp_res.status_code == 200
    comp_data = comp_res.json()
    assert comp_data["success"] is True
    assert "comparison_status" in comp_data
    assert "changed_regions" in comp_data
    assert "authentic_percentage" in comp_data

    # Check side-by-side artifact route
    art_res = client.get(f"/api/evidence/{ev_id}/forensic-artifact/reference_side_by_side")
    assert art_res.status_code == 200
    assert art_res.headers["content-type"] == "image/png"
