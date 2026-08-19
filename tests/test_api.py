from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "Truth Lens" in data["service"]

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

def test_startup_recovery_orphaned_jobs():
    from app.database import get_db, reconcile_orphaned_jobs
    import uuid
    from datetime import datetime

    test_ev_id = f"EV-TEST-ORPHAN-{uuid.uuid4().hex[:6]}"
    now = datetime.utcnow().isoformat() + "Z"

    # Insert an orphaned job in ANALYZING status
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO evidence (evidence_id, case_id, original_filename, stored_filename, file_size_bytes, 
                             mime_type, modality, sha256_hash, sha512_hash, md5_hash, uploaded_by, 
                             uploaded_at, status, pipeline_status, analysis_started_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_ev_id, "CASE-2026-001", "crashed_stream.mp4", "nonexistent.mp4", 5000,
            "video/mp4", "VIDEO", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "", "", "Officer Smith", now, "ANALYZING", "ANALYZING", now
        ))

    # Trigger reconciliation
    recovered = reconcile_orphaned_jobs()
    assert recovered >= 1

    # Check status endpoint
    status_res = client.get(f"/api/evidence/{test_ev_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["status"] == "FAILED"
    assert status_data["pipeline_status"] == "FAILED"
    assert "Analysis interrupted by server restart" in status_data["error_message"]

    # Check chain of custody
    custody_res = client.get(f"/api/custody?evidence_id={test_ev_id}")
    assert custody_res.status_code == 200
    events = custody_res.json()
    assert any(e["action"] == "ANALYSIS_FAILED" and "System Recovery" in e["actor"] for e in events)

def test_integrity_verification_states():
    from PIL import Image
    import io
    img_io = io.BytesIO()
    test_img = Image.new("RGB", (50, 50), color=(10, 20, 30))
    test_img.save(img_io, "PNG")
    file_bytes = img_io.getvalue()

    files = {"file": ("integrity_state_test.png", file_bytes, "image/png")}
    data = {"case_id": "CASE-2026-001", "uploaded_by": "Test Investigator"}

    upload_res = client.post("/api/evidence/upload", files=files, data=data)
    assert upload_res.status_code == 202
    ev_id = upload_res.json()["evidence_id"]
    sha256_recorded = upload_res.json()["sha256_hash"]

    # 1. Baseline preservation check (no reference hash provided)
    base_res = client.post(f"/api/evidence/{ev_id}/verify-integrity")
    assert base_res.status_code == 200
    base_data = base_res.json()
    assert base_data["is_valid"] is True
    assert base_data["status"] == "PRESERVED"

    # 2. Matching external reference check
    match_res = client.post(f"/api/evidence/{ev_id}/verify-integrity", json={"expected_sha256": sha256_recorded})
    assert match_res.status_code == 200
    match_data = match_res.json()
    assert match_data["is_valid"] is True
    assert match_data["status"] == "MATCH"

    # 3. Mismatched external reference check
    mismatch_res = client.post(f"/api/evidence/{ev_id}/verify-integrity", json={"expected_sha256": "0" * 64})
    assert mismatch_res.status_code == 200
    mismatch_data = mismatch_res.json()
    assert mismatch_data["is_valid"] is False
    assert mismatch_data["status"] == "MISMATCH"

def test_bulk_upload_mixed_batch():
    import io
    from PIL import Image
    
    # Valid image
    img_io = io.BytesIO()
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(img_io, "JPEG")
    valid_bytes = img_io.getvalue()
    
    # Valid doc
    valid_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n%%EOF\n"
    
    # Invalid extension
    invalid_bytes = b"bad executable payload"

    files = [
        ("files", ("batch_img1.jpg", valid_bytes, "image/jpeg")),
        ("files", ("batch_doc2.pdf", valid_pdf, "application/pdf")),
        ("files", ("batch_malicious.exe", invalid_bytes, "application/x-msdownload"))
    ]
    data = {"case_id": "CASE-BULK-TEST", "uploaded_by": "Bulk Examiner"}

    res = client.post("/api/evidence/upload-bulk", files=files, data=data)
    assert res.status_code == 202
    resp_data = res.json()
    assert resp_data["total_files"] == 3
    assert resp_data["accepted_count"] == 2
    assert resp_data["rejected_count"] == 1
    
    # Check items status
    items = resp_data["items"]
    assert items[0]["status"] == "ACCEPTED"
    assert items[0]["evidence_id"].startswith("EV-2026-")
    assert items[1]["status"] == "ACCEPTED"
    assert items[2]["status"] == "REJECTED"
    assert "Unsupported file extension" in items[2]["error"]

def test_bulk_upload_batch_limit_exceeded():
    files = [
        ("files", (f"file_{i}.jpg", b"fake", "image/jpeg")) for i in range(12)
    ]
    res = client.post("/api/evidence/upload-bulk", files=files, data={"case_id": "CASE-LIMIT-TEST"})
    assert res.status_code == 400
    assert "Maximum of 10 files" in res.json()["detail"]

def test_case_summary_and_evidence_endpoints():
    import io
    from PIL import Image
    case_id = "CASE-WORKSPACE-TEST"
    
    # Ingest 1 exhibit into this case
    img_io = io.BytesIO()
    Image.new("RGB", (32, 32), color=(50, 100, 150)).save(img_io, "JPEG")
    res = client.post("/api/evidence/upload", files={"file": ("workspace_sample.jpg", img_io.getvalue(), "image/jpeg")}, data={"case_id": case_id})
    assert res.status_code == 202

    # 1. Summary
    sum_res = client.get(f"/api/cases/{case_id}/summary")
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert sum_data["case_id"] == case_id
    assert sum_data["total_evidence"] >= 1
    assert "status_counts" in sum_data
    assert "risk_counts" in sum_data

    # 2. Evidence list
    ev_res = client.get(f"/api/cases/{case_id}/evidence")
    assert ev_res.status_code == 200
    ev_list = ev_res.json()
    assert len(ev_list) >= 1
    assert any(e["original_filename"] == "workspace_sample.jpg" for e in ev_list)

    # 3. Timeline
    time_res = client.get(f"/api/cases/{case_id}/timeline")
    assert time_res.status_code == 200
    events = time_res.json()
    assert len(events) >= 1
    assert any(e["action"] == "EVIDENCE_INGESTION" for e in events)

def test_case_summary_pdf_generation():
    case_id = "CASE-PDF-TEST"
    import io
    from PIL import Image
    img_io = io.BytesIO()
    Image.new("RGB", (32, 32), color=(50, 100, 150)).save(img_io, "JPEG")
    client.post("/api/evidence/upload", files={"file": ("pdf_sample.jpg", img_io.getvalue(), "image/jpeg")}, data={"case_id": case_id})

    res = client.get(f"/api/reports/cases/{case_id}/download")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert len(res.content) > 1000
    assert f"truth_lens_case_report_{case_id}.pdf" in res.headers.get("content-disposition", "")

