from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "EVIDENCE-X" in data["service"]

def test_dashboard_stats():
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_cases" in data
    assert "total_evidence" in data
    assert "risk_distribution" in data

def test_cases_api():
    # 1. List cases
    response = client.get("/api/cases")
    assert response.status_code == 200
    cases = response.json()
    assert len(cases) >= 1

    # 2. Create case
    case_payload = {
        "title": "Test Seized Drive Investigation",
        "description": "Analysis of recovered CCTV and social media files",
        "lead_investigator": "Officer Sharma"
    }
    create_res = client.post("/api/cases", json=case_payload)
    assert create_res.status_code == 200
    new_case = create_res.json()
    assert new_case["title"] == case_payload["title"]

def test_evidence_upload_and_flow():
    # Generate valid test JPEG bytes
    from PIL import Image
    import io
    img_io = io.BytesIO()
    test_img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    test_img.save(img_io, "JPEG")
    file_bytes = img_io.getvalue()

    files = {"file": ("test_evidence.jpg", file_bytes, "image/jpeg")}
    data = {
        "case_id": "CASE-2026-001",
        "uploaded_by": "Test Investigator",
        "notes": "Seized from primary witness smartphone"
    }
    
    upload_res = client.post("/api/evidence/upload", files=files, data=data)
    assert upload_res.status_code == 202
    upload_data = upload_res.json()
    evidence_id = upload_data["evidence_id"]
    assert evidence_id.startswith("EV-2026-")

    # Fetch evidence detail
    detail_res = client.get(f"/api/evidence/{evidence_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["evidence"]["evidence_id"] == evidence_id
    assert detail_data["forensic_result"] is not None
    assert len(detail_data["findings"]) > 0

    # On-demand verify integrity
    verify_res = client.post(f"/api/evidence/{evidence_id}/verify-integrity")
    assert verify_res.status_code == 200
    assert verify_res.json()["is_valid"] is True

    # Copilot query
    copilot_res = client.post("/api/copilot/query", json={
        "evidence_id": evidence_id,
        "question": "What is the integrity status of this evidence?"
    })
    assert copilot_res.status_code == 200
    assert "recorded SHA-256" in copilot_res.json()["answer"]

    # Report Download
    report_res = client.get(f"/api/reports/{evidence_id}/download")
    assert report_res.status_code == 200
    assert report_res.headers["content-type"] == "application/pdf"

    # Status endpoint check
    status_res = client.get(f"/api/evidence/{evidence_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["evidence_id"] == evidence_id
    assert status_data["status"] == "COMPLETED"
    assert status_data["pipeline_status"] == "COMPLETED"
    assert status_data["error_message"] is None

    # Raw file download check
    file_res = client.get(f"/api/evidence/{evidence_id}/file")
    assert file_res.status_code == 200

    # Forensic artifact check
    ela_res = client.get(f"/api/evidence/{evidence_id}/forensic-artifact/ela")
    assert ela_res.status_code == 200
    assert "image/jpeg" in ela_res.headers["content-type"]

def test_simulated_pipeline_failure():
    from unittest.mock import patch
    from PIL import Image
    import io

    img_io = io.BytesIO()
    test_img = Image.new("RGB", (64, 64), color=(200, 50, 50))
    test_img.save(img_io, "JPEG")
    file_bytes = img_io.getvalue()

    files = {"file": ("malformed_fail.jpg", file_bytes, "image/jpeg")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}

    with patch("app.api.routes_evidence.image_analyzer.analyze", side_effect=RuntimeError("Simulated Decoder Crash")):
        upload_res = client.post("/api/evidence/upload", files=files, data=data)
        assert upload_res.status_code == 202
        evidence_id = upload_res.json()["evidence_id"]

        status_res = client.get(f"/api/evidence/{evidence_id}/status")
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data["status"] == "FAILED"
        assert status_data["pipeline_status"] == "FAILED"
        assert "RuntimeError" in status_data["error_message"]

def test_cors_origins_configuration():
    # Allowed origin
    res_allowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res_allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Disallowed origin
    res_disallowed = client.options(
        "/api/health",
        headers={
            "Origin": "http://untrusted-adversary.com",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert res_disallowed.headers.get("access-control-allow-origin") != "http://untrusted-adversary.com"
    assert res_disallowed.headers.get("access-control-allow-origin") != "*"
