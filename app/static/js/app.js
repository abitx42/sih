// EVIDENCE-X Web Application Controller

let currentEvidenceId = null;
let currentEvidenceData = null;
let riskChartInstance = null;

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  loadDashboardData();
  loadCasesDropdown();
  setupDragAndDrop();
});

// View Navigation Router
function switchView(viewName) {
  document.querySelectorAll(".view-section").forEach(sec => sec.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach(btn => btn.classList.remove("active"));

  const targetSec = document.getElementById(`view-${viewName}`);
  if (targetSec) targetSec.classList.add("active");

  const navBtns = document.querySelectorAll(".nav-item");
  const mapping = { dashboard: 0, cases: 1, upload: 2, lab: 3, custody: 4 };
  if (navBtns[mapping[viewName]]) {
    navBtns[mapping[viewName]].classList.add("active");
  }

  if (viewName === "dashboard") loadDashboardData();
  if (viewName === "custody") loadCustodyLedger();
  if (viewName === "cases") loadCasesList();
}

function initNavigation() {
  switchView("dashboard");
}

// 1. Dashboard Operations
async function loadDashboardData() {
  try {
    const res = await fetch("/api/dashboard/stats");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("stat-cases").innerText = data.total_cases || 0;
    document.getElementById("stat-evidence").innerText = data.total_evidence || 0;
    document.getElementById("stat-high-risk").innerText = data.risk_distribution["HIGH RISK"] || 0;
    document.getElementById("stat-low-risk").innerText = data.risk_distribution["LOW RISK"] || 0;

    renderRiskChart(data.risk_distribution);
    renderDashboardEvidence(data.recent_evidence || []);
    renderDashboardCustody(data.recent_custody_events || []);
  } catch (err) {
    console.error("Dashboard stats error:", err);
  }
}

function renderRiskChart(riskDist) {
  const ctx = document.getElementById("riskChart");
  if (!ctx) return;

  const low = riskDist["LOW RISK"] || 0;
  const med = riskDist["REVIEW REQUIRED"] || 0;
  const high = riskDist["HIGH RISK"] || 0;

  if (riskChartInstance) riskChartInstance.destroy();

  riskChartInstance = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Low Risk", "Review Req.", "High Risk"],
      datasets: [{
        data: [low, med, high],
        backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
        borderColor: "#111827",
        borderWidth: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#94a3b8", font: { size: 11 } }
        }
      }
    }
  });
}

function renderDashboardEvidence(items) {
  const tbody = document.getElementById("dashboard-recent-table");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim);">No digital evidence ingested yet. Click '+ New Ingestion' to upload.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(item => {
    let riskBadge = `<span class="badge badge-low">LOW RISK</span>`;
    if (item.risk_category === "HIGH RISK") riskBadge = `<span class="badge badge-high">HIGH RISK</span>`;
    else if (item.risk_category === "REVIEW REQUIRED") riskBadge = `<span class="badge badge-medium">REVIEW REQ.</span>`;

    return `
      <tr>
        <td><strong>${item.evidence_id}</strong></td>
        <td>${item.original_filename}</td>
        <td><span class="badge badge-modality">${item.modality}</span></td>
        <td><span class="hash-mono">${item.sha256_hash.substring(0, 16)}...</span></td>
        <td>${riskBadge} (${item.forensic_risk_score || 0}/100)</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openEvidenceInLab('${item.evidence_id}')">Inspect Lab</button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderDashboardCustody(events) {
  const tbody = document.getElementById("dashboard-custody-table");
  if (!tbody) return;

  if (events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim);">No custody events recorded.</td></tr>`;
    return;
  }

  tbody.innerHTML = events.map(e => `
    <tr>
      <td style="color: var(--text-muted); font-size: 0.8rem;">${(e.timestamp || '').substring(0, 19).replace('T', ' ')}</td>
      <td><strong>${e.evidence_id}</strong></td>
      <td><span class="badge badge-modality">${e.action}</span></td>
      <td>${e.actor}</td>
      <td><span class="hash-mono">${(e.recorded_sha256 || '').substring(0, 12)}...</span></td>
      <td style="font-size: 0.82rem;">${e.details}</td>
    </tr>
  `).join("");
}

// 2. Evidence Ingestion & Drag and Drop
function setupDragAndDrop() {
  const dropzone = document.getElementById("upload-dropzone");
  if (!dropzone) return;

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, preventDefaults, false);
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.add('dragover'), false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => dropzone.classList.remove('dragover'), false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
      document.getElementById('file-input').files = files;
      handleFileSelected({ target: { files: files } });
    }
  });
}

function handleFileSelected(e) {
  const file = e.target.files[0];
  if (!file) return;

  const preview = document.getElementById("selected-file-preview");
  const filename = document.getElementById("preview-filename");
  const filesize = document.getElementById("preview-filesize");
  const modality = document.getElementById("preview-modality");

  filename.innerText = file.name;
  filesize.innerText = `${(file.size / 1024).toFixed(1)} KB`;

  const ext = file.name.split('.').pop().toLowerCase();
  if (['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tiff'].includes(ext)) modality.innerText = "IMAGE";
  else if (['mp4', 'avi', 'mov', 'mkv', 'webm'].includes(ext)) modality.innerText = "VIDEO";
  else if (['wav', 'mp3', 'ogg', 'flac', 'm4a'].includes(ext)) modality.innerText = "AUDIO";
  else if (['pdf', 'docx', 'xlsx', 'pptx', 'txt'].includes(ext)) modality.innerText = "DOCUMENT";
  else if (['zip', 'tar', 'gz', '7z'].includes(ext)) modality.innerText = "ARCHIVE";
  else modality.innerText = "MEDIA";

  preview.style.display = "block";
}

async function handleEvidenceUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById("file-input");
  if (!fileInput.files[0]) {
    alert("Please select a digital evidence file to ingest.");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("case_id", document.getElementById("upload-case-id").value);
  formData.append("uploaded_by", document.getElementById("upload-actor").value);
  formData.append("notes", document.getElementById("upload-notes").value);

  const form = document.getElementById("evidence-upload-form");
  const progress = document.getElementById("upload-progress-box");
  form.style.display = "none";
  progress.style.display = "block";

  try {
    const res = await fetch("/api/evidence/upload", {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      alert(`Upload failed: ${err.detail || 'Unknown error'}`);
      form.style.display = "block";
      progress.style.display = "none";
      return;
    }

    const data = await res.json();
    openEvidenceInLab(data.evidence_id);
  } catch (err) {
    alert(`Upload error: ${err}`);
    form.style.display = "block";
    progress.style.display = "none";
  }
}

// 3. Forensic Lab / Evidence Detail
async function openEvidenceInLab(evidenceId) {
  currentEvidenceId = evidenceId;
  switchView("lab");

  try {
    const res = await fetch(`/api/evidence/${evidenceId}`);
    if (!res.ok) return;
    const data = await res.json();
    currentEvidenceData = data;

    renderLabView(data);
  } catch (err) {
    console.error("Lab detail error:", err);
  }
}

function renderLabView(data) {
  const ev = data.evidence;
  const res = data.forensic_result || {};
  const findings = data.findings || [];
  const rawMetrics = res.raw_metrics_json || {};

  document.getElementById("lab-evidence-id").innerText = ev.evidence_id;
  document.getElementById("lab-filename").innerText = `${ev.original_filename} (${(ev.file_size_bytes / 1024).toFixed(1)} KB)`;
  document.getElementById("lab-modality-badge").innerText = ev.modality;
  document.getElementById("lab-sha256-snippet").innerText = `SHA-256: ${ev.sha256_hash}`;

  // Composite Risk Score & Category
  const riskScore = res.forensic_risk_score !== undefined ? res.forensic_risk_score : 0;
  const riskCat = res.risk_category || "UNKNOWN";
  const riskBadge = document.getElementById("lab-risk-badge");
  const riskScoreEl = document.getElementById("lab-risk-score");

  riskScoreEl.innerText = `${riskScore}/100`;
  riskBadge.innerText = riskCat;

  if (riskCat === "HIGH RISK") {
    riskBadge.className = "badge badge-high";
    riskScoreEl.style.color = "var(--risk-high)";
  } else if (riskCat === "REVIEW REQUIRED") {
    riskBadge.className = "badge badge-medium";
    riskScoreEl.style.color = "var(--risk-medium)";
  } else {
    riskBadge.className = "badge badge-low";
    riskScoreEl.style.color = "var(--risk-low)";
  }

  // AI Manipulation Indicator (ML Vision Model)
  const aiScoreEl = document.getElementById("lab-ai-score");
  const modelStatus = res.model_status || "AVAILABLE";
  const modelIndicator = res.ai_manipulation_indicator;

  if (modelStatus === "AVAILABLE" && modelIndicator !== null && modelIndicator !== undefined) {
    const aiPct = (modelIndicator * 100).toFixed(1);
    aiScoreEl.innerText = `${aiPct}%`;
    aiScoreEl.style.color = aiPct > 70 ? "var(--risk-high)" : (aiPct > 35 ? "var(--risk-medium)" : "var(--risk-low)");
  } else if (modelStatus === "ANALYSIS INCONCLUSIVE") {
    aiScoreEl.innerText = "INCONCLUSIVE";
    aiScoreEl.style.color = "var(--risk-medium)";
  } else {
    aiScoreEl.innerText = "UNAVAILABLE";
    aiScoreEl.style.color = "var(--text-dim)";
  }
  
  if (ev.modality === "VIDEO") {
    const sampled = rawMetrics.sampled_frames_count || 0;
    const analysed = rawMetrics.ml_detector ? rawMetrics.ml_detector.analysed_frame_count : 0;
    document.getElementById("lab-ai-model").innerText = `${res.ai_model_name || "ViT Detector"} (${analysed}/${sampled} frames)`;
  } else if (ev.modality === "AUDIO") {
    document.getElementById("lab-ai-model").innerText = "Acoustic Signal Forensics (No Local ML Model)";
  } else {
    document.getElementById("lab-ai-model").innerText = res.ai_model_name || "ViT Image Detector";
  }

  // Heuristic Forensic Anomaly Score (ELA / FFT / Temporal / Acoustic / Noise)
  const heuristicScore = res.forensic_anomaly_score !== undefined ? res.forensic_anomaly_score : 0;
  document.getElementById("lab-heuristic-score").innerText = `${heuristicScore}/100`;

  // Provenance
  const provStatus = res.provenance_status || "NOT_AVAILABLE";
  const provDetails = rawMetrics.provenance ? rawMetrics.provenance.details : "No C2PA manifest attached.";
  document.getElementById("lab-provenance-detail").innerText = `Provenance: ${provStatus.replace('_', ' ')} • ${provDetails.substring(0, 45)}...`;

  // Visual Exhibits
  const origImg = document.getElementById("exhibit-orig");
  const forensicImg = document.getElementById("exhibit-forensic");
  const forensicTitle = document.getElementById("exhibit-forensic-title");

  if (ev.modality === "IMAGE") {
    origImg.src = `/api/evidence/${ev.evidence_id}/file`;
    forensicImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/ela`;
    forensicTitle.innerText = "Exhibit 2: Error Level Analysis (ELA 95% Heatmap)";
    forensicImg.style.display = "block";
  } else if (ev.modality === "VIDEO") {
    origImg.src = "https://placehold.co/400x200/111827/94a3b8?text=Video+Stream+Exhibit";
    forensicImg.src = "https://placehold.co/400x200/111827/94a3b8?text=Uniform+Frame+Sampling+Stream";
    forensicTitle.innerText = `Exhibit 2: Uniform Keyframe Sequence (${rawMetrics.sampled_frames_count || 0} Frames Decoded)`;
    forensicImg.style.display = "block";
  } else if (ev.modality === "AUDIO") {
    origImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/waveform`;
    forensicImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/spectrogram`;
    forensicTitle.innerText = `Exhibit 2: STFT Spectrogram & Splicing Analysis (${rawMetrics.sample_rate_hz || 0}Hz)`;
    forensicImg.style.display = "block";
  } else {
    origImg.src = "https://placehold.co/400x200/111827/94a3b8?text=Document+Stream";
    forensicImg.style.display = "none";
    forensicTitle.innerText = "Non-Visual Structural Verification";
  }

  // Findings Table
  document.getElementById("lab-findings-count").innerText = `${findings.length} Signals Evaluated`;
  const findingsTable = document.getElementById("lab-findings-table");
  if (findings.length === 0) {
    findingsTable.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim);">No anomalies detected. Baseline clean.</td></tr>`;
  } else {
    findingsTable.innerHTML = findings.map(f => {
      let sevClass = "badge-low";
      if (f.severity === "CRITICAL" || f.severity === "HIGH") sevClass = "badge-high";
      else if (f.severity === "MEDIUM") sevClass = "badge-medium";

      return `
        <tr>
          <td><strong>${f.signal_name}</strong></td>
          <td><span class="badge badge-modality">${f.category}</span></td>
          <td><span class="badge ${sevClass}">${f.severity}</span></td>
          <td>${f.score}/100</td>
          <td style="font-size: 0.83rem; line-height: 1.35;">${f.explanation}</td>
        </tr>
      `;
    }).join("");
  }

  // Copilot Narrative & Recommendations
  document.getElementById("copilot-narrative").innerText = res.summary_narrative || "No narrative generated.";
  const recEl = document.getElementById("copilot-recommendations");
  if (res.recommendations) {
    recEl.innerHTML = res.recommendations.split('\n').join('<br>');
  } else {
    recEl.innerText = "No specific investigator recommendations.";
  }
}

// 4. On-Demand Integrity Re-Verification
async function reverifyIntegrity() {
  if (!currentEvidenceId) return;

  try {
    const res = await fetch(`/api/evidence/${currentEvidenceId}/verify-integrity`, { method: "POST" });
    if (!res.ok) return;
    const data = await res.json();

    const dot = document.getElementById("lab-integrity-dot");
    const text = document.getElementById("lab-integrity-text");

    if (data.is_valid) {
      dot.style.background = "var(--risk-low)";
      text.innerText = "VERIFIED (MATCH)";
      text.style.color = "var(--risk-low)";
      alert(`✅ Cryptographic File-Integrity Verified!\n\nRecorded Hash: ${data.recorded_sha256}\nCurrent Hash:  ${data.current_sha256}\n\nBit-level integrity is intact.\n(Note: Integrity certifies file preservation, not content authenticity.)`);
    } else {
      dot.style.background = "var(--risk-high)";
      text.innerText = "INTEGRITY MISMATCH";
      text.style.color = "var(--risk-high)";
      alert(`⚠️ SECURITY ALERT: Cryptographic Integrity Mismatch!\n\nThe file on disk has been altered since baseline recording.`);
    }
  } catch (err) {
    alert(`Verification error: ${err}`);
  }
}

// 5. Download Forensic Report (PDF)
function downloadForensicReport() {
  if (!currentEvidenceId) return;
  window.open(`/api/reports/${currentEvidenceId}/download`, '_blank');
}

// 6. Forensic Copilot Interactive Chat
async function handleCopilotChat(e) {
  e.preventDefault();
  const input = document.getElementById("copilot-user-input");
  const question = input.value.trim();
  if (!question || !currentEvidenceId) return;

  const chatMessages = document.getElementById("copilot-chat-messages");

  const userBubble = document.createElement("div");
  userBubble.className = "chat-bubble user";
  userBubble.innerText = question;
  chatMessages.appendChild(userBubble);
  input.value = "";
  chatMessages.scrollTop = chatMessages.scrollHeight;

  const assistantBubble = document.createElement("div");
  assistantBubble.className = "chat-bubble assistant";
  assistantBubble.innerText = "Consulting automated forensic signals & models...";
  chatMessages.appendChild(assistantBubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const res = await fetch("/api/copilot/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ evidence_id: currentEvidenceId, question: question })
    });

    if (!res.ok) {
      assistantBubble.innerText = "Copilot query failed. Please retry.";
      return;
    }

    const data = await res.json();
    assistantBubble.innerText = data.answer;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  } catch (err) {
    assistantBubble.innerText = `Error: ${err}`;
  }
}

// 7. Full Custody Ledger & Cases
async function loadCustodyLedger() {
  try {
    const res = await fetch("/api/custody");
    if (!res.ok) return;
    const events = await res.json();

    const tbody = document.getElementById("full-custody-table");
    if (!tbody) return;

    if (events.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim);">No custody records found.</td></tr>`;
      return;
    }

    tbody.innerHTML = events.map(e => `
      <tr>
        <td><strong>${e.event_id}</strong></td>
        <td style="color: var(--text-muted); font-size: 0.8rem;">${(e.timestamp || '').substring(0, 19).replace('T', ' ')}</td>
        <td><strong>${e.evidence_id}</strong></td>
        <td><span class="badge badge-modality">${e.action}</span></td>
        <td>${e.actor}</td>
        <td><span class="hash-mono">${(e.recorded_sha256 || '').substring(0, 16)}...</span></td>
        <td style="font-size: 0.82rem;">${e.details}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Custody ledger load error:", err);
  }
}

function exportCustodyJSON() {
  window.open("/api/custody/export", "_blank");
}

async function loadCasesList() {
  try {
    const res = await fetch("/api/cases");
    if (!res.ok) return;
    const cases = await res.json();

    const tbody = document.getElementById("cases-table");
    if (!tbody) return;

    tbody.innerHTML = cases.map(c => `
      <tr>
        <td><strong>${c.case_id}</strong></td>
        <td>${c.title}</td>
        <td>${c.lead_investigator}</td>
        <td style="color: var(--text-muted); font-size: 0.8rem;">${(c.created_at || '').substring(0, 10)}</td>
        <td><span class="badge badge-modality">${c.evidence_count || 0} Exhibits</span></td>
        <td><span class="badge badge-low">${c.status}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Cases load error:", err);
  }
}

async function loadCasesDropdown() {
  try {
    const res = await fetch("/api/cases");
    if (!res.ok) return;
    const cases = await res.json();
    const select = document.getElementById("upload-case-id");
    if (!select) return;

    select.innerHTML = cases.map(c => `<option value="${c.case_id}">${c.case_id} - ${c.title}</option>`).join("");
  } catch (err) {
    console.error("Cases dropdown error:", err);
  }
}

function openNewCaseModal() {
  const caseTitle = prompt("Enter Investigation Case Title:");
  if (!caseTitle) return;
  const leadInvestigator = prompt("Enter Lead Forensic Investigator Name:", "Insp. Rajesh Verma (Digital Forensics Unit)");
  if (!leadInvestigator) return;

  fetch("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: caseTitle,
      lead_investigator: leadInvestigator
    })
  }).then(res => res.json()).then(data => {
    alert(`Case '${data.case_id}' created successfully!`);
    loadCasesList();
    loadCasesDropdown();
  });
}
