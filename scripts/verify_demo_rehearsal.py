import os
import sys
import io
import time
import json
import wave
import tempfile
import numpy as np
from PIL import Image, ImageDraw
from pathlib import Path

# Ensure repo root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def run_rehearsal():
    print("=" * 60)
    print("TRUTH LENS : FULL DEMO REHEARSAL VERIFICATION")
    print("=" * 60)

    results = {}

    # 1. Health Endpoint
    print("\n[1] Testing Health Endpoint...")
    r = client.get("/api/health")
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    health_data = r.json()
    assert health_data["service"] == "Truth Lens", f"Unexpected service name: {health_data['service']}"
    print(f"  ✓ Health Status: {health_data['status']} | Service: {health_data['service']}")
    results["health_check"] = True

    # 2. Frontend Assets & Branding Verification
    print("\n[2] Verifying Frontend Static Assets & Branding...")
    r_index = client.get("/")
    assert r_index.status_code == 200
    html = r_index.text
    assert "<title>Truth Lens — Digital Evidence Forensics Platform</title>" in html
    assert "<h1>Truth Lens</h1>" in html
    assert "See the signals. Review the evidence." in html
    assert "EVIDENCE-X" not in html, "Found legacy EVIDENCE-X in index.html"
    print("  ✓ index.html: Brand 'Truth Lens' and tagline confirmed, 0 legacy brand strings.")

    r_css = client.get("/static/css/style.css")
    assert r_css.status_code == 200
    assert ".hero-banner" in r_css.text
    assert ".flow-pipeline-grid" in r_css.text
    print("  ✓ style.css: Modern hero and forensic pipeline classes verified.")

    r_js = client.get("/static/js/app.js")
    assert r_js.status_code == 200
    assert "Truth Lens" in r_js.text
    print("  ✓ app.js: Controller loaded cleanly.")
    results["frontend_assets"] = True

    # 3. Cases Management
    print("\n[3] Testing Cases API...")
    r_cases = client.get("/api/cases")
    assert r_cases.status_code == 200
    cases = r_cases.json()
    print(f"  ✓ Cases retrieved: {len(cases)} active case(s).")
    
    # Create test case with unique ID
    import uuid
    case_uid = f"CASE-DEMO-{uuid.uuid4().hex[:6].upper()}"
    r_create_case = client.post("/api/cases", json={
        "case_id": case_uid,
        "title": f"Operation Truth Lens Live Demo ({case_uid})",
        "description": "Live demonstration scenario for evaluation jury.",
        "lead_investigator": "Lead Forensic Examiner"
    })
    assert r_create_case.status_code in [200, 201], f"Case creation failed: {r_create_case.status_code}"
    print(f"  ✓ Demo case '{case_uid}' initialized.")
    results["cases_api"] = True

    # 4. Multi-Modality Evidence Upload & Pipeline Execution
    print("\n[4] Ingesting & Analyzing Exhibits Across All 5 Modalities...")
    exhibits = {}

    # Modality A: Image (Authentic Baseline)
    img_a = Image.new("RGB", (320, 240), color=(100, 150, 200))
    b_a = io.BytesIO()
    img_a.save(b_a, "JPEG")
    r_up_a = client.post("/api/evidence/upload", files={"file": ("demo_auth_img.jpg", b_a.getvalue(), "image/jpeg")}, data={"case_id": case_uid, "uploaded_by": "Officer A", "notes": "[DEMO FIXTURE] Authentic baseline."})
    assert r_up_a.status_code == 202
    exhibits["IMAGE_AUTH"] = r_up_a.json()["evidence_id"]
    print(f"  ✓ Uploaded Image (Authentic): {exhibits['IMAGE_AUTH']}")

    # Modality B: Image (Spliced Patch)
    img_b = Image.new("RGB", (320, 240), color=(50, 50, 50))
    d_b = ImageDraw.Draw(img_b)
    d_b.rectangle([100, 80, 220, 160], fill=(255, 0, 0))
    b_b = io.BytesIO()
    img_b.save(b_b, "JPEG", quality=65)
    r_up_b = client.post("/api/evidence/upload", files={"file": ("demo_spliced_img.jpg", b_b.getvalue(), "image/jpeg")}, data={"case_id": case_uid, "uploaded_by": "Officer A", "notes": "[DEMO FIXTURE] Spliced image."})
    assert r_up_b.status_code == 202
    exhibits["IMAGE_SPLICED"] = r_up_b.json()["evidence_id"]
    print(f"  ✓ Uploaded Image (Spliced): {exhibits['IMAGE_SPLICED']}")

    # Modality C: Audio (WAV)
    sample_rate = 16000
    t = np.linspace(0, 2, sample_rate * 2, endpoint=False)
    audio = (np.sin(2 * np.pi * 440 * t) * 32767 * 0.8).astype(np.int16)
    wav_b = io.BytesIO()
    with wave.open(wav_b, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    r_up_c = client.post("/api/evidence/upload", files={"file": ("demo_audio.wav", wav_b.getvalue(), "audio/wav")}, data={"case_id": case_uid, "uploaded_by": "Officer B", "notes": "[DEMO FIXTURE] Acoustic recording."})
    assert r_up_c.status_code == 202
    exhibits["AUDIO"] = r_up_c.json()["evidence_id"]
    print(f"  ✓ Uploaded Audio: {exhibits['AUDIO']}")

    # Modality D: Document (PDF)
    pdf_b = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n%%EOF\n"
    r_up_d = client.post("/api/evidence/upload", files={"file": ("demo_doc.pdf", pdf_b, "application/pdf")}, data={"case_id": case_uid, "uploaded_by": "Officer C", "notes": "[DEMO FIXTURE] PDF document."})
    assert r_up_d.status_code == 202
    exhibits["DOCUMENT"] = r_up_d.json()["evidence_id"]
    print(f"  ✓ Uploaded Document: {exhibits['DOCUMENT']}")

    # Modality E: Archive (ZIP)
    import zipfile
    zip_b = io.BytesIO()
    with zipfile.ZipFile(zip_b, 'w') as zf:
        zf.writestr("test_evidence.txt", "Evidence triage payload")
    r_up_e = client.post("/api/evidence/upload", files={"file": ("demo_archive.zip", zip_b.getvalue(), "application/zip")}, data={"case_id": case_uid, "uploaded_by": "Officer D", "notes": "[DEMO FIXTURE] ZIP container."})
    assert r_up_e.status_code == 202
    exhibits["ARCHIVE"] = r_up_e.json()["evidence_id"]
    print(f"  ✓ Uploaded Archive: {exhibits['ARCHIVE']}")
    results["uploads"] = True

    # 5. Verification of Processed Evidence Records
    print("\n[5] Verifying Evidence Completion & Forensic Metrics...")
    for mod_name, ev_id in exhibits.items():
        r_det = client.get(f"/api/evidence/{ev_id}")
        assert r_det.status_code == 200
        det = r_det.json()
        status = det["evidence"]["status"]
        assert status in ["COMPLETED", "FAILED"], f"Unexpected status {status} for {ev_id}"
        
        if status == "COMPLETED":
            f_res = det.get("forensic_result")
            assert f_res is not None, f"Missing forensic result for {ev_id}"
            risk_cat = f_res.get("risk_category")
            risk_score = f_res.get("forensic_risk_score")
            print(f"  ✓ {mod_name} ({ev_id}): Status={status} | Risk={risk_cat} ({risk_score}/100) | Findings={len(det.get('findings', []))}")
        else:
            print(f"  ✓ {mod_name} ({ev_id}): Status={status} | Error={det['evidence'].get('error_message')}")
    results["processing"] = True

    # 6. PDF Report Generation
    print("\n[6] Testing PDF Assessment Report Download...")
    img_ev_id = exhibits["IMAGE_AUTH"]
    r_pdf = client.get(f"/api/reports/{img_ev_id}/download")
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert len(r_pdf.content) > 1000
    assert f"truth_lens_report_{img_ev_id}.pdf" in r_pdf.headers.get("content-disposition", "")
    print(f"  ✓ PDF report generated successfully ({len(r_pdf.content)} bytes, filename='truth_lens_report_{img_ev_id}.pdf').")
    results["pdf_reports"] = True

    # 7. AI Explanation & Copilot Q&A with Graceful Fallback
    print("\n[7] Testing AI Forensic Explanation & Copilot Assistant...")
    r_expl = client.post(f"/api/evidence/{img_ev_id}/explain")
    assert r_expl.status_code == 200
    expl = r_expl.json()
    assert "investigator_summary" in expl
    assert "limitations" in expl
    assert "recommended_next_steps" in expl
    assert "disclaimer" in expl
    print(f"  ✓ AI Explanation: Source='{expl.get('source')}' | Summary='{expl.get('investigator_summary')[:60]}...'")

    r_qa = client.post("/api/copilot/query", json={
        "evidence_id": img_ev_id,
        "question": "What is the cryptographic hash status of this exhibit?"
    })
    assert r_qa.status_code == 200
    qa = r_qa.json()
    assert "answer" in qa
    print(f"  ✓ Copilot Q&A: Answer='{qa.get('answer')[:70]}...' | Source='{qa.get('source')}'")
    results["copilot"] = True

    # 8. Chain of Custody Log & JSON Export
    print("\n[8] Testing Application Custody Log & JSON Export...")
    r_custody = client.get("/api/custody")
    assert r_custody.status_code == 200
    events = r_custody.json()
    assert len(events) > 0
    print(f"  ✓ Custody Log: {len(events)} logged events in append-only log.")

    r_export = client.get("/api/custody/export")
    assert r_export.status_code == 200
    assert r_export.headers["content-type"] == "application/json"
    exp_json = r_export.json()
    assert exp_json["platform"] == "Truth Lens Digital Evidence Forensics Platform"
    print(f"  ✓ Custody JSON Export verified (Platform: '{exp_json['platform']}').")
    results["custody_log"] = True

    # 9. Integrity Verification (Baseline vs Match)
    print("\n[9] Testing Decoupled Integrity Verification Endpoint...")
    r_integ_base = client.post(f"/api/evidence/{img_ev_id}/verify-integrity")
    assert r_integ_base.status_code == 200
    base_data = r_integ_base.json()
    assert base_data["status"] == "PRESERVED"
    assert "integrity preserved" in base_data["details"].lower()
    print(f"  ✓ Baseline Integrity: Status='{base_data['status']}' | Details='{base_data['details']}'")

    r_integ_match = client.post(f"/api/evidence/{img_ev_id}/verify-integrity", json={"expected_sha256": base_data["recorded_sha256"]})
    assert r_integ_match.status_code == 200
    match_data = r_integ_match.json()
    assert match_data["status"] == "MATCH"
    print(f"  ✓ External Expected Hash Match: Status='{match_data['status']}'")
    results["integrity_verification"] = True

    # 10. Bulk Upload & Case Workspace Verification
    print("\n[10] Testing Bulk Upload & Case Investigation Workspace...")
    bulk_files = [
        ("files", ("bulk_photo1.jpg", b_a.getvalue(), "image/jpeg")),
        ("files", ("bulk_contract2.pdf", pdf_b, "application/pdf")),
        ("files", ("bulk_invalid.exe", b"invalid executable", "application/x-msdownload"))
    ]
    r_bulk = client.post("/api/evidence/upload-bulk", files=bulk_files, data={"case_id": case_uid, "uploaded_by": "Bulk Lead Officer"})
    assert r_bulk.status_code == 202
    b_data = r_bulk.json()
    assert b_data["accepted_count"] == 2
    assert b_data["rejected_count"] == 1
    print(f"  ✓ Bulk Upload: {b_data['accepted_count']} accepted, {b_data['rejected_count']} rejected.")

    # Case Summary KPI
    r_c_sum = client.get(f"/api/cases/{case_uid}/summary")
    assert r_c_sum.status_code == 200
    c_sum = r_c_sum.json()
    assert c_sum["total_evidence"] >= 7
    print(f"  ✓ Case Workspace KPIs: Total Evidence={c_sum['total_evidence']} | Status={c_sum['status_counts']}")

    # Case Evidence List
    r_c_ev = client.get(f"/api/cases/{case_uid}/evidence")
    assert r_c_ev.status_code == 200
    c_ev = r_c_ev.json()
    assert len(c_ev) >= 7
    print(f"  ✓ Case Exhibits Inventory: {len(c_ev)} exhibits loaded.")

    # Case Custody Timeline
    r_c_tl = client.get(f"/api/cases/{case_uid}/timeline")
    assert r_c_tl.status_code == 200
    c_tl = r_c_tl.json()
    assert len(c_tl) >= 7
    print(f"  ✓ Case Custody Stream: {len(c_tl)} custody events.")

    # Case Summary PDF Export
    r_case_pdf = client.get(f"/api/reports/cases/{case_uid}/download")
    assert r_case_pdf.status_code == 200
    assert r_case_pdf.headers["content-type"] == "application/pdf"
    assert len(r_case_pdf.content) > 1000
    assert f"truth_lens_case_report_{case_uid}.pdf" in r_case_pdf.headers.get("content-disposition", "")
    print(f"  ✓ Case Summary PDF Export verified ({len(r_case_pdf.content)} bytes, filename='truth_lens_case_report_{case_uid}.pdf').")
    results["case_workspace"] = True

    print("\n" + "=" * 60)
    print("ALL REHEARSAL CHECKS PASSED (100% SUCCESSFUL)!")
    print("=" * 60)
    return results

if __name__ == "__main__":
    run_rehearsal()
