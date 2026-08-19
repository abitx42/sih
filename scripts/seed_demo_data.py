import os
import sys
import io
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
from app.config import STORAGE_DIR

client = TestClient(app)

def create_demo_media():
    print("Generating Truth Lens demo digital evidence exhibits...")

    # 1. Authentic Seized Photograph (Low Risk)
    img_auth = Image.new("RGB", (640, 480), color=(140, 180, 220))
    draw = ImageDraw.Draw(img_auth)
    draw.rectangle([50, 50, 590, 430], outline=(255, 255, 255), width=3)
    draw.text((70, 70), "Exhibit A: Field Surveillance Baseline [DEMO FIXTURE]", fill=(255, 255, 255))
    
    img_auth_bytes = io.BytesIO()
    img_auth.save(img_auth_bytes, "JPEG", quality=90)
    
    res1 = client.post("/api/evidence/upload", files={
        "file": ("demo_surveillance_cctv_frame_01.jpg", img_auth_bytes.getvalue(), "image/jpeg")
    }, data={
        "case_id": "CASE-2026-001",
        "uploaded_by": "Insp. Rajesh Verma (Digital Forensics Unit)",
        "notes": "[DEMO FIXTURE - NOT REAL EVIDENCE] Baseline frame captured from bank ATM perimeter camera."
    })
    print("Created Authentic Exhibit (IMAGE):", res1.json().get("evidence_id"))

    # 2. Manipulated/Edited Exhibit with Spliced Patch (High Risk)
    img_mod = Image.new("RGB", (640, 480), color=(80, 90, 110))
    draw_m = ImageDraw.Draw(img_mod)
    draw_m.rectangle([200, 150, 440, 330], fill=(255, 50, 50), outline=(255, 255, 0), width=4)
    draw_m.text((220, 220), "INPAINTED / SPLICED REGION [DEMO]", fill=(255, 255, 255))
    
    img_mod_bytes = io.BytesIO()
    img_mod.save(img_mod_bytes, "JPEG", quality=70)
    
    res2 = client.post("/api/evidence/upload", files={
        "file": ("demo_suspect_social_media_deepfake.jpg", img_mod_bytes.getvalue(), "image/jpeg")
    }, data={
        "case_id": "CASE-2026-001",
        "uploaded_by": "Insp. Rajesh Verma (Digital Forensics Unit)",
        "notes": "[DEMO FIXTURE - NOT REAL EVIDENCE] Viral social media post submitted as alleged proof of financial fraud."
    })
    print("Created Manipulated Exhibit (IMAGE):", res2.json().get("evidence_id"))

    # 3. Audio Recording (WAV with sharp spectral cuts and silence)
    sample_rate = 22050
    t = np.linspace(0, 3, int(sample_rate * 3), endpoint=False)
    tone1 = np.sin(2 * np.pi * 440 * t[:sample_rate])
    tone2 = np.zeros(int(sample_rate * 0.5))  # silence pause
    tone3 = np.sin(2 * np.pi * 1200 * t[int(sample_rate*1.5):])
    audio_data = np.concatenate([tone1, tone2, tone3])
    audio_scaled = (audio_data * 32767 * 0.8).astype(np.int16)

    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_f:
        wav_f.setnchannels(1)
        wav_f.setsampwidth(2)
        wav_f.setframerate(sample_rate)
        wav_f.writeframes(audio_scaled.tobytes())

    res3 = client.post("/api/evidence/upload", files={
        "file": ("demo_extortion_voicemail_call.wav", wav_io.getvalue(), "audio/wav")
    }, data={
        "case_id": "CASE-2026-001",
        "uploaded_by": "Sub-Insp. Priya Nair (Audio Forensics Lab)",
        "notes": "[DEMO FIXTURE - NOT REAL EVIDENCE] Voicemail recording recovered from complainant phone."
    })
    print("Created Audio Exhibit (AUDIO):", res3.json().get("evidence_id"))

    # 4. Multi-revision PDF document
    pdf_data = (
        b"%PDF-1.5\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"%%EOF\n"
        b"4 0 obj\n<< /Producer (OnlinePDFModifier) /ModDate (D:20260819120000Z) >>\nendobj\n"
        b"%%EOF\n"
    )
    res4 = client.post("/api/evidence/upload", files={
        "file": ("demo_contract_agreement_v2.pdf", pdf_data, "application/pdf")
    }, data={
        "case_id": "CASE-2026-001",
        "uploaded_by": "Insp. Rajesh Verma",
        "notes": "[DEMO FIXTURE - NOT REAL EVIDENCE] Digitally signed procurement tender document."
    })
    print("Created Document Exhibit (DOCUMENT):", res4.json().get("evidence_id"))

    # 5. Forensic Archive Exhibit (ZIP)
    import zipfile
    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("seized_device_manifest.txt", "Truth Lens Demo Extraction Manifest\nDevice: iPhone 13\nStatus: Seized\n")
        zf.writestr("network_connection_log.csv", "timestamp,src_ip,dest_ip,port\n2026-08-19T10:00:00Z,192.168.1.100,10.0.0.1,443\n")
    
    res5 = client.post("/api/evidence/upload", files={
        "file": ("demo_seized_usb_triage.zip", zip_io.getvalue(), "application/zip")
    }, data={
        "case_id": "CASE-2026-001",
        "uploaded_by": "Lead Forensic Examiner",
        "notes": "[DEMO FIXTURE - NOT REAL EVIDENCE] Triage container extracted from seized hardware media."
    })
    print("Created Archive Exhibit (ARCHIVE):", res5.json().get("evidence_id"))

    # 6. Surveillance Video Exhibit (MP4)
    try:
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_vid:
            tmp_vid_path = tmp_vid.name
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(tmp_vid_path, fourcc, 10.0, (320, 240))
        for frame_num in range(20):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(frame, f"CCTV CAM 04 - F:{frame_num} [DEMO]", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            out.write(frame)
        out.release()

        with open(tmp_vid_path, "rb") as f_vid:
            vid_bytes = f_vid.read()
        os.remove(tmp_vid_path)

        res6 = client.post("/api/evidence/upload", files={
            "file": ("demo_security_perimeter_cam.mp4", vid_bytes, "video/mp4")
        }, data={
            "case_id": "CASE-2026-001",
            "uploaded_by": "Insp. Rajesh Verma",
            "notes": "[DEMO FIXTURE - NOT REAL EVIDENCE] Digital video recorder stream segment."
        })
        print("Created Video Exhibit (VIDEO):", res6.json().get("evidence_id"))
    except Exception as e:
        print(f"Video exhibit creation skipped: {e}")

    print("Demo dataset seeded successfully!")

if __name__ == "__main__":
    create_demo_media()
