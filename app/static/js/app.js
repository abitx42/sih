// Truth Lens Web Application Controller

let currentEvidenceId = null;
let currentEvidenceData = null;
let riskChartInstance = null;

// HTML Entity Escaping (XSS Prevention)
function escapeHTML(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

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

    const safeId = escapeHTML(item.evidence_id);
    const safeFilename = escapeHTML(item.original_filename);
    const safeModality = escapeHTML(item.modality);
    const safeHash = escapeHTML(item.sha256_hash ? item.sha256_hash.substring(0, 16) : "");

    return `
      <tr>
        <td><strong>${safeId}</strong></td>
        <td>${safeFilename}</td>
        <td><span class="badge badge-modality">${safeModality}</span></td>
        <td><span class="hash-mono">${safeHash}...</span></td>
        <td>${riskBadge} (${item.forensic_risk_score || 0}/100)</td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="openEvidenceInLab('${safeId}')">Inspect Lab</button>
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
      <td style="color: var(--text-muted); font-size: 0.8rem;">${escapeHTML((e.timestamp || '').substring(0, 19).replace('T', ' '))}</td>
      <td><strong>${escapeHTML(e.evidence_id)}</strong></td>
      <td><span class="badge badge-modality">${escapeHTML(e.action)}</span></td>
      <td>${escapeHTML(e.actor)}</td>
      <td><span class="hash-mono">${escapeHTML((e.recorded_sha256 || '').substring(0, 12))}...</span></td>
      <td style="font-size: 0.82rem;">${escapeHTML(e.details)}</td>
    </tr>
  `).join("");
}

// 2. Evidence Ingestion & Multi-File Drag and Drop
let selectedFiles = [];

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
    const files = Array.from(dt.files);
    if (files.length > 0) {
      handleFiles(files);
    }
  });
}

function handleFileSelected(e) {
  const files = Array.from(e.target.files);
  if (files.length > 0) {
    handleFiles(files);
  }
}

function handleFiles(files) {
  const maxBatch = 10;
  for (const f of files) {
    if (selectedFiles.length >= maxBatch) {
      alert(`Maximum batch limit reached (${maxBatch} files per upload).`);
      break;
    }
    // Prevent exact duplicates in queue
    if (!selectedFiles.some(sf => sf.name === f.name && sf.size === f.size)) {
      selectedFiles.push(f);
    }
  }
  renderSelectedFiles();
}

function removeSelectedFile(index) {
  selectedFiles.splice(index, 1);
  renderSelectedFiles();
}

function clearSelectedFiles() {
  selectedFiles = [];
  const fileInput = document.getElementById("file-input");
  if (fileInput) fileInput.value = "";
  renderSelectedFiles();
}

function detectModalityByName(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  if (['jpg', 'jpeg', 'png', 'webp', 'bmp', 'tiff'].includes(ext)) return "IMAGE";
  if (['mp4', 'avi', 'mov', 'mkv', 'webm'].includes(ext)) return "VIDEO";
  if (['wav', 'mp3', 'ogg', 'flac', 'm4a'].includes(ext)) return "AUDIO";
  if (['pdf', 'docx', 'xlsx', 'pptx', 'txt'].includes(ext)) return "DOCUMENT";
  if (['zip', 'tar', 'gz', '7z'].includes(ext)) return "ARCHIVE";
  return "MEDIA";
}

function renderSelectedFiles() {
  const container = document.getElementById("selected-files-container");
  const list = document.getElementById("selected-files-list");
  const countSpan = document.getElementById("selected-files-count");
  if (!container || !list) return;

  if (selectedFiles.length === 0) {
    container.style.display = "none";
    list.innerHTML = "";
    return;
  }

  container.style.display = "block";
  if (countSpan) countSpan.innerText = selectedFiles.length;

  list.innerHTML = selectedFiles.map((file, idx) => {
    const mod = detectModalityByName(file.name);
    return `
      <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); padding: 0.5rem 0.8rem; border-radius: 6px; border: 1px solid var(--border-color); font-size: 0.82rem;">
        <div style="display: flex; align-items: center; gap: 0.6rem; overflow: hidden;">
          <span class="badge badge-modality">${mod}</span>
          <strong style="color: #fff; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; max-width: 320px;">${escapeHTML(file.name)}</strong>
          <span style="color: var(--text-dim); font-size: 0.75rem;">(${(file.size / 1024).toFixed(1)} KB)</span>
        </div>
        <button type="button" onclick="removeSelectedFile(${idx})" style="background: none; border: none; color: #ef4444; cursor: pointer; font-size: 1rem; padding: 0 0.3rem;">✕</button>
      </div>
    `;
  }).join("");
}

let selectedAnalysisMode = "FULL_ANALYSIS";

function updateAnalysisMode(mode) {
  selectedAnalysisMode = mode;
  document.querySelectorAll('.mode-pill').forEach(pill => pill.classList.remove('active'));
  if (mode === "QUICK_SCAN") {
    const p = document.getElementById("pill-quick");
    if (p) p.classList.add("active");
  } else if (mode === "ADVANCED_INVESTIGATION") {
    const p = document.getElementById("pill-advanced");
    if (p) p.classList.add("active");
  } else {
    const p = document.getElementById("pill-full");
    if (p) p.classList.add("active");
  }
  const badge = document.getElementById("pipeline-active-mode-badge");
  if (badge) badge.innerText = mode.replace(/_/g, ' ');
}

async function updateLivePipelineStages(evidenceId) {
  try {
    const res = await fetch(`/api/evidence/${evidenceId}/pipeline-progress`);
    if (!res.ok) return;
    const prog = await res.json();
    const grid = document.getElementById("pipeline-stages-grid");
    if (!grid) return;

    const stages = prog.stages || {};
    const stageKeys = [
      { key: "INTEGRITY_BASELINE", label: "1. Integrity Baseline" },
      { key: "METADATA_PROVENANCE", label: "2. Metadata & C2PA" },
      { key: "AI_DETECTOR_ENSEMBLE", label: "3. Multi-AI Ensemble" },
      { key: "PIXEL_FORENSICS", label: "4. ELA & Sensor Noise" },
      { key: "LOCAL_REGION_ANALYSIS", label: "5. Patch Localizer" },
      { key: "EXTERNAL_DETECTORS", label: "6. External Adapter" },
      { key: "EVIDENCE_CORRELATION", label: "7. Signal Synthesis" }
    ];

    grid.innerHTML = stageKeys.map(s => {
      const info = stages[s.key] || { status: "QUEUED", details: "Waiting..." };
      let statusBadge = `<span class="badge" style="background: rgba(148,163,184,0.1); color: #94a3b8; font-size: 0.65rem;">○ QUEUED</span>`;
      if (info.status === "COMPLETED") {
        statusBadge = `<span class="badge badge-low" style="font-size: 0.65rem;">✓ COMPLETE</span>`;
      } else if (info.status === "ANALYZING") {
        statusBadge = `<span class="badge badge-status-analyzing" style="font-size: 0.65rem;">⟳ ANALYZING</span>`;
      } else if (info.status === "SKIPPED") {
        statusBadge = `<span class="badge" style="background: rgba(100,116,139,0.2); color: #64748b; font-size: 0.65rem;">— SKIPPED</span>`;
      } else if (info.status === "FAILED") {
        statusBadge = `<span class="badge badge-high" style="font-size: 0.65rem;">✕ FAILED</span>`;
      }

      return `
        <div class="pipeline-stage-card">
          <div class="stage-title">
            <span>${escapeHTML(s.label)}</span>
            ${statusBadge}
          </div>
          <div class="stage-details" title="${escapeHTML(info.details || '')}">${escapeHTML(info.details || 'Waiting for stage trigger')}</div>
        </div>
      `;
    }).join("");
  } catch (e) {
    console.warn("Pipeline progress poll err:", e);
  }
}

async function pollSingleEvidence(evidenceId, cardElem) {
  const maxAttempts = 60;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      // Update live stage progress
      updateLivePipelineStages(evidenceId);

      const res = await fetch(`/api/evidence/${evidenceId}/status`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === "COMPLETED" || data.pipeline_status === "COMPLETED") {
          updateLivePipelineStages(evidenceId);
          cardElem.className = "bulk-queue-item completed";
          cardElem.querySelector(".status-col").innerHTML = `
            <span class="badge badge-low" style="background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3);">✓ COMPLETED</span>
          `;
          cardElem.querySelector(".action-col").innerHTML = `
            <button class="btn btn-primary" style="padding: 0.35rem 0.7rem; font-size: 0.75rem;" onclick="openEvidenceInLab('${evidenceId}')">🔬 Open in Lab</button>
          `;
          return { success: true, evidenceId };
        }
        if (data.status === "FAILED" || data.pipeline_status === "FAILED") {
          updateLivePipelineStages(evidenceId);
          cardElem.className = "bulk-queue-item failed";
          cardElem.querySelector(".status-col").innerHTML = `
            <span class="badge badge-high" style="background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3);">✕ FAILED</span>
          `;
          cardElem.querySelector(".action-col").innerHTML = `
            <span style="font-size: 0.72rem; color: #ef4444;">${escapeHTML(data.error_message || 'Analysis error')}</span>
          `;
          return { success: false, evidenceId, error: data.error_message };
        }
      }
    } catch (e) {
      console.warn("Poll single evidence error:", e);
    }
    await new Promise(r => setTimeout(r, 2000));
  }
  return { success: false, evidenceId, error: "Timed out" };
}

async function handleEvidenceUpload(e) {
  e.preventDefault();
  const fileInput = document.getElementById("file-input");
  
  if (selectedFiles.length === 0 && fileInput && fileInput.files.length > 0) {
    selectedFiles = Array.from(fileInput.files);
  }

  if (selectedFiles.length === 0) {
    alert("Please select at least one digital evidence file to ingest.");
    return;
  }

  const caseId = document.getElementById("upload-case-id").value;
  const actor = document.getElementById("upload-actor").value;
  const notes = document.getElementById("upload-notes").value;

  const formData = new FormData();
  for (const f of selectedFiles) {
    formData.append("files", f);
  }
  formData.append("case_id", caseId);
  formData.append("uploaded_by", actor);
  formData.append("notes", notes);
  formData.append("analysis_mode", selectedAnalysisMode);

  const form = document.getElementById("evidence-upload-form");
  const progressBox = document.getElementById("upload-progress-box");
  const queueContainer = document.getElementById("bulk-queue-items");
  const summaryBadge = document.getElementById("batch-progress-summary");
  const titleElem = document.getElementById("batch-progress-title");

  form.style.display = "none";
  progressBox.style.display = "block";
  queueContainer.innerHTML = "";
  summaryBadge.className = "badge badge-status-analyzing";
  summaryBadge.innerText = `Ingesting ${selectedFiles.length} exhibit(s)...`;
  titleElem.innerText = `Ingesting Batch into ${caseId}`;

  try {
    const res = await fetch("/api/evidence/upload-bulk", {
      method: "POST",
      body: formData
    });

    if (!res.ok && res.status !== 202) {
      const err = await res.json();
      alert(`Bulk ingestion failed: ${escapeHTML(err.detail || 'Unknown error')}`);
      form.style.display = "block";
      progressBox.style.display = "none";
      return;
    }

    const bulkData = await res.json();
    const items = bulkData.items || [];

    // Render queue cards
    queueContainer.innerHTML = items.map((item, idx) => {
      const isAccepted = item.status === "ACCEPTED";
      const mod = item.modality || detectModalityByName(item.original_filename);
      return `
        <div class="bulk-queue-item" id="queue-item-${idx}">
          <div style="display: flex; align-items: center; gap: 0.75rem; min-width: 200px;">
            <span class="badge badge-modality">${mod}</span>
            <div>
              <strong style="color: #fff; font-size: 0.85rem;">${escapeHTML(item.original_filename)}</strong>
              <div style="font-size: 0.72rem; color: var(--text-dim);">${item.evidence_id ? escapeHTML(item.evidence_id) : 'Rejection notice'}</div>
            </div>
          </div>

          <div class="status-col">
            ${isAccepted 
              ? `<span class="badge badge-status-analyzing">⏳ ANALYZING</span>` 
              : `<span class="badge badge-high">✕ REJECTED</span>`}
          </div>

          <div class="action-col" style="min-width: 130px; text-align: right;">
            ${isAccepted 
              ? `<span style="font-size: 0.75rem; color: var(--text-dim);">Running heuristics...</span>` 
              : `<span style="font-size: 0.72rem; color: #ef4444;">${escapeHTML(item.error || 'Invalid file')}</span>`}
          </div>
        </div>
      `;
    }).join("");

    // Start concurrent polling for all accepted items
    const pollPromises = [];
    items.forEach((item, idx) => {
      if (item.status === "ACCEPTED" && item.evidence_id) {
        const card = document.getElementById(`queue-item-${idx}`);
        pollPromises.push(pollSingleEvidence(item.evidence_id, card));
      }
    });

    // Wait for all polls to finish
    await Promise.all(pollPromises);

    summaryBadge.className = "badge badge-low";
    summaryBadge.innerText = `Batch Complete (${bulkData.accepted_count} Analyzed, ${bulkData.rejected_count} Rejected)`;
    titleElem.innerText = `Batch Analysis Completed for ${caseId}`;

    // Reload dropdown and cases list in background
    loadDashboardData();
    loadCasesDropdown();

  } catch (err) {
    alert(`Bulk upload error: ${escapeHTML(String(err))}`);
    form.style.display = "block";
    progressBox.style.display = "none";
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

  document.getElementById("lab-evidence-id").textContent = ev.evidence_id;
  document.getElementById("lab-filename").textContent = `${ev.original_filename} (${(ev.file_size_bytes / 1024).toFixed(1)} KB)`;
  document.getElementById("lab-modality-badge").textContent = ev.modality;
  const shaSnippet = document.getElementById("lab-sha256-snippet");
  if (shaSnippet) shaSnippet.textContent = `SHA-256: ${ev.sha256_hash}`;
  // Conflict Alert Banner
  const ensemble = res.ensemble_agreement || rawMetrics.ensemble_agreement;
  const conflictBanner = document.getElementById("lab-conflict-banner");
  const conflictText = document.getElementById("lab-conflict-text");
  if (conflictBanner) {
    if (ensemble && ensemble.has_signal_conflict) {
      conflictBanner.style.display = "block";
      if (conflictText && ensemble.conflict_description) {
        conflictText.innerText = ensemble.conflict_description;
      }
    } else {
      conflictBanner.style.display = "none";
    }
  }

  // Multi-Specialist Consensus Agreement Card
  const consensusPanel = document.getElementById("lab-consensus-panel");
  if (consensusPanel) {
    if (ensemble && Array.isArray(ensemble.specialist_breakdown) && ensemble.specialist_breakdown.length > 0) {
      consensusPanel.style.display = "block";
      const badgeEl = document.getElementById("lab-consensus-badge");
      const sumTextEl = document.getElementById("lab-consensus-summary-text");
      const ratioTextEl = document.getElementById("lab-consensus-ratio-text");
      const meterManip = document.getElementById("meter-fill-manipulated");
      const meterAuth = document.getElementById("meter-fill-authentic");
      const gridEl = document.getElementById("lab-specialists-grid");

      if (badgeEl) badgeEl.innerText = ensemble.consensus_label || "Consensus Evaluated";
      if (sumTextEl) sumTextEl.innerText = `Consensus Strength: ${ensemble.consensus_verdict.replace(/_/g, ' ')} (${ensemble.agreement_percentage || 0}%)`;
      if (ratioTextEl) ratioTextEl.innerText = `${ensemble.manipulated_signals_count || 0} Manipulated • ${ensemble.authentic_signals_count || 0} Authentic`;

      const totalDecisive = (ensemble.manipulated_signals_count || 0) + (ensemble.authentic_signals_count || 0);
      const manipPct = totalDecisive > 0 ? ((ensemble.manipulated_signals_count || 0) / totalDecisive) * 100 : 50;
      const authPct = 100 - manipPct;

      if (meterManip) meterManip.style.width = `${manipPct}%`;
      if (meterAuth) meterAuth.style.width = `${authPct}%`;

      if (gridEl) {
        gridEl.innerHTML = ensemble.specialist_breakdown.map(s => {
          const v = s.verdict || "N/A";
          let vBadge = `<span class="badge badge-medium">${escapeHTML(v)}</span>`;
          if (v === "MANIPULATED") vBadge = `<span class="badge badge-high">🔴 MANIPULATED</span>`;
          else if (v === "AUTHENTIC") vBadge = `<span class="badge badge-low">🟢 AUTHENTIC</span>`;
          else if (v === "SKIPPED") vBadge = `<span class="badge" style="background: rgba(100,116,139,0.2); color: #94a3b8;">⚪ SKIPPED</span>`;

          const indVal = s.indicator !== null && s.indicator !== undefined ? `${(s.indicator * 100).toFixed(1)}%` : (s.score !== undefined ? `${s.score}/100` : (s.provenance_status || 'N/A'));

          return `
            <div class="specialist-card">
              <div class="specialist-card-header">
                <span class="specialist-card-title">${escapeHTML(s.name)}</span>
                ${vBadge}
              </div>
              <div class="specialist-card-focus">🎯 ${escapeHTML(s.focus || '')}</div>
              <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem;">
                <span>Score / Metric: <strong style="color: #fff;">${escapeHTML(String(indVal))}</strong></span>
                <span>Latency: <strong style="color: var(--accent-cyan);">${s.latency_ms || 0}ms</strong></span>
              </div>
              <div class="specialist-card-details">${escapeHTML(s.details || '')}</div>
            </div>
          `;
        }).join("");
      }
    } else {
      consensusPanel.style.display = "none";
    }
  }

  // Composite Risk Score & Category
  const riskScore = res.forensic_risk_score !== undefined ? res.forensic_risk_score : 0;
  const riskCat = res.risk_category || "UNKNOWN";
  const riskBadge = document.getElementById("lab-risk-badge");
  const riskScoreEl = document.getElementById("lab-risk-score");

  riskScoreEl.textContent = `${riskScore}/100`;
  riskBadge.textContent = riskCat;

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

  // Forensic Authenticity Taxonomy
  const taxonomy = res.forensic_taxonomy || rawMetrics.forensic_taxonomy || "ANALYSIS_INCONCLUSIVE";
  const taxBadge = document.getElementById("lab-taxonomy-badge");
  if (taxBadge) {
    if (taxonomy === "LIKELY_AUTHENTIC") {
      taxBadge.className = "taxonomy-badge taxonomy-likely-authentic";
      taxBadge.innerHTML = "🔍 LIKELY AUTHENTIC";
    } else if (taxonomy === "LIKELY_AI_GENERATED") {
      taxBadge.className = "taxonomy-badge taxonomy-likely-ai-generated";
      taxBadge.innerHTML = "🤖 LIKELY AI-GENERATED";
    } else if (taxonomy === "LIKELY_AI_ASSISTED_MANIPULATION") {
      taxBadge.className = "taxonomy-badge taxonomy-likely-ai-assisted";
      taxBadge.innerHTML = "✨ LIKELY AI-ASSISTED MANIPULATION";
    } else if (taxonomy === "LIKELY_TRADITIONAL_MANIPULATION") {
      taxBadge.className = "taxonomy-badge taxonomy-likely-traditional";
      taxBadge.innerHTML = "✂️ LIKELY TRADITIONAL MANIPULATION";
    } else {
      taxBadge.className = "taxonomy-badge taxonomy-inconclusive";
      taxBadge.innerHTML = "❓ ANALYSIS INCONCLUSIVE";
    }
  }

  // Multi-Signal "WHY + WHERE + HOW" Correlation Card
  const corrCard = document.getElementById("lab-correlation-card");
  const corr = rawMetrics.correlation_summary;
  if (corrCard && corr) {
    corrCard.style.display = "block";
    const sigCount = document.getElementById("wwh-signals-count");
    if (sigCount) sigCount.innerText = `${corr.signal_agreement_count || 0} Elevated Indicator(s)`;

    const whereEl = document.getElementById("wwh-where-content");
    if (whereEl && Array.isArray(corr.where_locations)) {
      whereEl.innerHTML = corr.where_locations.map(loc => `
        <div style="margin-bottom: 0.3rem;">
          <strong style="color: #fff;">${escapeHTML(loc.label || 'ROI')}</strong>
          <div style="font-size: 0.75rem; color: var(--accent-cyan);">${escapeHTML(loc.anomaly_type || 'Anomaly')} (Score: ${loc.score || 0}%)</div>
        </div>
      `).join("");
    }

    const whatEl = document.getElementById("wwh-what-content");
    if (whatEl && Array.isArray(corr.what_observations)) {
      whatEl.innerHTML = corr.what_observations.slice(0, 3).map(obs => `
        <div style="font-size: 0.78rem; margin-bottom: 0.25rem; color: var(--text-main);">• ${escapeHTML(obs)}</div>
      `).join("");
    }

    const howEl = document.getElementById("wwh-how-content");
    if (howEl) howEl.innerText = corr.how_mechanism || "Continuous optical sensor imaging pipeline.";

    const whyEl = document.getElementById("wwh-why-content");
    if (whyEl) whyEl.innerText = corr.why_conclusion || "Multi-signal evaluation completed.";
  } else if (corrCard) {
    corrCard.style.display = "none";
  }

  // Heuristic Forensic Anomaly Score (ELA / FFT / Temporal / Acoustic / Noise / Patch Localizer)
  const heuristicScore = res.forensic_anomaly_score !== undefined ? res.forensic_anomaly_score : 0;
  document.getElementById("lab-heuristic-score").textContent = `${heuristicScore}/100`;

  // Provenance
  const provStatus = res.provenance_status || "NOT_AVAILABLE";
  const provDetails = rawMetrics.provenance ? rawMetrics.provenance.details : "No C2PA manifest attached.";
  document.getElementById("lab-provenance-detail").textContent = `Provenance: ${provStatus.replace(/_/g, ' ')} • ${provDetails.substring(0, 45)}...`;

  // Visual Exhibits
  const origImg = document.getElementById("exhibit-orig");
  const heatmapBox = document.getElementById("box-exhibit-heatmap");
  const heatmapImg = document.getElementById("exhibit-heatmap");
  const forensicImg = document.getElementById("exhibit-forensic");
  const forensicTitle = document.getElementById("exhibit-forensic-title");

  if (ev.modality === "IMAGE") {
    origImg.src = `/api/evidence/${ev.evidence_id}/file`;
    origImg.style.display = "block";

    if (heatmapBox && heatmapImg) {
      heatmapImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/manipulation_heatmap`;
      heatmapBox.style.display = "block";
    }

    forensicImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/ela`;
    forensicTitle.textContent = "Exhibit 3: Error Level Analysis (ELA 95% Heatmap)";
    forensicImg.style.display = "block";
  } else if (ev.modality === "VIDEO") {
    origImg.src = `/api/evidence/${ev.evidence_id}/file`;
    origImg.style.display = "block";
    if (heatmapBox) heatmapBox.style.display = "none";

    if (rawMetrics.sampled_frames_count > 0) {
      forensicImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/video_frame`;
      forensicTitle.textContent = `Exhibit 2: Decoded Video Keyframe (${rawMetrics.sampled_frames_count || 0} Frames Sampled)`;
      forensicImg.style.display = "block";
    } else {
      forensicImg.style.display = "none";
      forensicTitle.textContent = "Exhibit 2: No Decoded Frames Available";
    }
  } else if (ev.modality === "AUDIO") {
    if (heatmapBox) heatmapBox.style.display = "none";
    origImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/waveform`;
    forensicImg.src = `/api/evidence/${ev.evidence_id}/forensic-artifact/spectrogram`;
    forensicTitle.textContent = `Exhibit 2: STFT Spectrogram & Splicing Analysis (${rawMetrics.sample_rate_hz || 0}Hz)`;
    origImg.style.display = "block";
    forensicImg.style.display = "block";
  } else {
    if (heatmapBox) heatmapBox.style.display = "none";
    origImg.style.display = "none";
    forensicImg.style.display = "none";
    forensicTitle.textContent = "Non-Visual Structural Verification";
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
          <td><strong>${escapeHTML(f.signal_name)}</strong></td>
          <td><span class="badge badge-modality">${escapeHTML(f.category)}</span></td>
          <td><span class="badge ${sevClass}">${escapeHTML(f.severity)}</span></td>
          <td>${f.score}/100</td>
          <td style="font-size: 0.83rem; line-height: 1.35;">${escapeHTML(f.explanation)}</td>
        </tr>
      `;
    }).join("");
  }

  // Copilot Narrative & Recommendations
  document.getElementById("copilot-narrative").innerText = res.summary_narrative || "No narrative generated.";
  const recEl = document.getElementById("copilot-recommendations");
  if (res.recommendations) {
    recEl.innerHTML = escapeHTML(res.recommendations).split('\n').join('<br>');
  } else {
    recEl.innerText = "No specific investigator recommendations.";
  }

  // Bitstream Integrity / Baseline Status
  const integrityDot = document.getElementById("lab-integrity-dot");
  const integrityText = document.getElementById("lab-integrity-text");
  const integrityStatus = res.integrity_status || "RECORDED";
  if (integrityStatus === "MISMATCH") {
    integrityDot.style.background = "var(--risk-high)";
    integrityText.textContent = "INTEGRITY MISMATCH";
    integrityText.style.color = "var(--risk-high)";
  } else if (integrityStatus === "MATCH") {
    integrityDot.style.background = "var(--risk-low)";
    integrityText.textContent = "MATCH (REFERENCE)";
    integrityText.style.color = "var(--risk-low)";
  } else {
    integrityDot.style.background = "var(--risk-low)";
    integrityText.textContent = "RECORDED (BASELINE)";
    integrityText.style.color = "var(--risk-low)";
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
      text.innerText = "PRESERVED (BASELINE MATCH)";
      text.style.color = "var(--risk-low)";
      alert(`✅ Cryptographic File-Integrity Verified!\n\nRecorded Hash: ${data.recorded_sha256}\nCurrent Hash:  ${data.current_sha256}\n\nBit-level integrity is preserved against recorded baseline.\n(Note: Integrity certifies bitstream preservation, not content authenticity.)`);
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
        <td><strong>${escapeHTML(e.event_id)}</strong></td>
        <td style="color: var(--text-muted); font-size: 0.8rem;">${escapeHTML((e.timestamp || '').substring(0, 19).replace('T', ' '))}</td>
        <td><strong>${escapeHTML(e.evidence_id)}</strong></td>
        <td><span class="badge badge-modality">${escapeHTML(e.action)}</span></td>
        <td>${escapeHTML(e.actor)}</td>
        <td><span class="hash-mono">${escapeHTML((e.recorded_sha256 || '').substring(0, 16))}...</span></td>
        <td style="font-size: 0.82rem;">${escapeHTML(e.details)}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Custody ledger load error:", err);
  }
}

function exportCustodyJSON() {
  window.open("/api/custody/export", "_blank");
}

// 7. Case Management & Investigation Workspace
let currentCaseId = null;
let currentCaseEvidence = [];

async function loadCasesList() {
  try {
    const res = await fetch("/api/cases");
    if (!res.ok) return;
    const cases = await res.json();

    const tbody = document.getElementById("cases-table");
    if (!tbody) return;

    if (cases.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 1.5rem;">No cases created yet. Click "+ Create New Case" above.</td></tr>`;
      return;
    }

    tbody.innerHTML = cases.map(c => `
      <tr>
        <td><strong>${escapeHTML(c.case_id)}</strong></td>
        <td>${escapeHTML(c.title)}</td>
        <td>${escapeHTML(c.lead_investigator)}</td>
        <td style="color: var(--text-muted); font-size: 0.8rem;">${escapeHTML((c.created_at || '').substring(0, 10))}</td>
        <td><span class="badge badge-modality">${c.evidence_count || 0} Exhibits</span></td>
        <td><span class="badge badge-low">${escapeHTML(c.status)}</span></td>
        <td>
          <button class="btn btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.75rem;" onclick="openCaseWorkspace('${escapeHTML(c.case_id)}')">
            📂 Open Workspace
          </button>
        </td>
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

    select.innerHTML = cases.map(c => `<option value="${escapeHTML(c.case_id)}">${escapeHTML(c.case_id)} - ${escapeHTML(c.title)}</option>`).join("");
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
    openCaseWorkspace(data.case_id);
  });
}

async function openCaseWorkspace(caseId) {
  currentCaseId = caseId;
  switchView("cases");

  const listPanel = document.getElementById("cases-list-panel");
  const wsPanel = document.getElementById("case-workspace-panel");
  if (listPanel) listPanel.style.display = "none";
  if (wsPanel) wsPanel.style.display = "block";

  // Reset filters
  const searchInput = document.getElementById("ws-filter-search");
  const modSelect = document.getElementById("ws-filter-modality");
  const stSelect = document.getElementById("ws-filter-status");
  const rkSelect = document.getElementById("ws-filter-risk");
  const sortSelect = document.getElementById("ws-filter-sort");
  if (searchInput) searchInput.value = "";
  if (modSelect) modSelect.value = "ALL";
  if (stSelect) stSelect.value = "ALL";
  if (rkSelect) rkSelect.value = "ALL";
  if (sortSelect) sortSelect.value = "newest";

  try {
    const [summaryRes, evidenceRes, timelineRes] = await Promise.all([
      fetch(`/api/cases/${caseId}/summary`),
      fetch(`/api/cases/${caseId}/evidence`),
      fetch(`/api/cases/${caseId}/timeline`)
    ]);

    if (!summaryRes.ok) {
      alert("Failed to load case summary.");
      return;
    }

    const summary = await summaryRes.json();
    const evidenceList = evidenceRes.ok ? await evidenceRes.json() : [];
    const timeline = timelineRes.ok ? await timelineRes.json() : [];

    // Header
    document.getElementById("ws-case-id").innerText = summary.case_id;
    document.getElementById("ws-case-status").innerText = summary.status;
    document.getElementById("ws-case-title").innerText = summary.title;
    document.getElementById("ws-case-lead").innerText = `Lead Investigator: ${summary.lead_investigator} • Created: ${(summary.created_at || '').substring(0, 10)}`;

    // KPIs
    document.getElementById("ws-kpi-total").innerText = summary.total_evidence;
    
    const sc = summary.status_counts || {};
    document.getElementById("ws-kpi-status-counts").innerText = `${sc.COMPLETED || 0} Done`;
    document.getElementById("ws-kpi-status-sub").innerText = `${sc.ANALYZING || 0} Analyzing • ${sc.FAILED || 0} Failed`;

    const rc = summary.risk_counts || {};
    document.getElementById("ws-kpi-risk-summary").innerHTML = `
      <span style="color: var(--risk-low);">${rc['LOW RISK'] || 0} Low</span> • 
      <span style="color: var(--risk-medium);">${rc['REVIEW REQUIRED'] || 0} Review</span> • 
      <span style="color: var(--risk-high);">${rc['HIGH RISK'] || 0} High</span>
    `;

    document.getElementById("ws-kpi-latest-ts").innerText = summary.latest_analysis 
      ? summary.latest_analysis.substring(0, 19).replace('T', ' ') 
      : 'Never';

    // Store evidence and render table
    currentCaseEvidence = evidenceList;
    applyCaseFilters();

    // Render Timeline
    const tlContainer = document.getElementById("case-timeline-container");
    if (tlContainer) {
      if (timeline.length === 0) {
        tlContainer.innerHTML = `<div style="color: var(--text-dim); font-size: 0.85rem; text-align: center; padding: 1rem;">No custody events recorded for this case yet.</div>`;
      } else {
        tlContainer.innerHTML = timeline.map(event => `
          <div class="case-timeline-entry">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
              <div>
                <strong style="color: #fff;">${escapeHTML(event.action)}</strong>
                <span style="color: var(--accent-cyan); font-size: 0.75rem; margin-left: 0.5rem;">[${escapeHTML(event.evidence_id)}]</span>
              </div>
              <span style="color: var(--text-dim); font-size: 0.75rem;">${escapeHTML((event.timestamp || '').substring(0, 19).replace('T', ' '))} UTC</span>
            </div>
            <div style="color: var(--text-muted); margin-bottom: 0.25rem;">Actor: <strong style="color: var(--text-main);">${escapeHTML(event.actor)}</strong></div>
            <div style="color: var(--text-dim); font-size: 0.78rem;">${escapeHTML(event.details)}</div>
          </div>
        `).join("");
      }
    }

  } catch (err) {
    console.error("Case workspace error:", err);
  }
}

function backToCasesList() {
  const listPanel = document.getElementById("cases-list-panel");
  const wsPanel = document.getElementById("case-workspace-panel");
  if (listPanel) listPanel.style.display = "block";
  if (wsPanel) wsPanel.style.display = "none";
  currentCaseId = null;
  currentCaseEvidence = [];
  loadCasesList();
}

function applyCaseFilters() {
  const searchInput = document.getElementById("ws-filter-search");
  const modSelect = document.getElementById("ws-filter-modality");
  const stSelect = document.getElementById("ws-filter-status");
  const rkSelect = document.getElementById("ws-filter-risk");
  const sortSelect = document.getElementById("ws-filter-sort");

  const q = (searchInput ? searchInput.value : "").trim().toLowerCase();
  const mod = modSelect ? modSelect.value : "ALL";
  const st = stSelect ? stSelect.value : "ALL";
  const rk = rkSelect ? rkSelect.value : "ALL";
  const sortOpt = sortSelect ? sortSelect.value : "newest";

  let filtered = currentCaseEvidence.filter(item => {
    // Query search
    if (q) {
      const matchName = (item.original_filename || '').toLowerCase().includes(q);
      const matchId = (item.evidence_id || '').toLowerCase().includes(q);
      const matchHash = (item.sha256_hash || '').toLowerCase().includes(q);
      if (!matchName && !matchId && !matchHash) return false;
    }

    // Modality filter
    if (mod !== "ALL" && (item.modality || '').toUpperCase() !== mod) return false;

    // Status filter
    if (st !== "ALL" && (item.status || '').toUpperCase() !== st) return false;

    // Risk filter
    if (rk !== "ALL" && (item.risk_category || '').toUpperCase() !== rk) return false;

    return true;
  });

  // Sorting
  filtered.sort((a, b) => {
    if (sortOpt === "newest") {
      return (b.uploaded_at || '').localeCompare(a.uploaded_at || '');
    } else if (sortOpt === "oldest") {
      return (a.uploaded_at || '').localeCompare(b.uploaded_at || '');
    } else if (sortOpt === "risk_high") {
      return (b.forensic_risk_score || 0) - (a.forensic_risk_score || 0);
    } else if (sortOpt === "filename") {
      return (a.original_filename || '').localeCompare(b.original_filename || '');
    }
    return 0;
  });

  // Render Table
  const tbody = document.getElementById("case-evidence-table-body");
  const emptyState = document.getElementById("case-empty-state");
  const countSpan = document.getElementById("ws-evidence-count");
  const table = document.getElementById("case-evidence-table");

  if (countSpan) countSpan.innerText = filtered.length;

  if (filtered.length === 0) {
    if (tbody) tbody.innerHTML = "";
    if (table) table.style.display = "none";
    if (emptyState) emptyState.style.display = "block";
    return;
  }

  if (table) table.style.display = "table";
  if (emptyState) emptyState.style.display = "none";

  if (tbody) {
    tbody.innerHTML = filtered.map(item => {
      let riskBadge = `<span class="badge" style="background: rgba(100,116,139,0.2); color: #94a3b8;">PENDING</span>`;
      if (item.risk_category === "LOW RISK") {
        riskBadge = `<span class="badge badge-low">LOW (${item.forensic_risk_score ? item.forensic_risk_score.toFixed(1) : '0'}%)</span>`;
      } else if (item.risk_category === "REVIEW REQUIRED") {
        riskBadge = `<span class="badge badge-medium">REVIEW (${item.forensic_risk_score ? item.forensic_risk_score.toFixed(1) : '0'}%)</span>`;
      } else if (item.risk_category === "HIGH RISK") {
        riskBadge = `<span class="badge badge-high">HIGH (${item.forensic_risk_score ? item.forensic_risk_score.toFixed(1) : '0'}%)</span>`;
      }

      let statusBadge = `<span class="badge badge-status-analyzing">⏳ ANALYZING</span>`;
      if (item.status === "COMPLETED") {
        statusBadge = `<span class="badge badge-low">✓ COMPLETED</span>`;
      } else if (item.status === "FAILED") {
        statusBadge = `<span class="badge badge-high">✕ FAILED</span>`;
      }

      return `
        <tr>
          <td><strong style="color: #fff;">${escapeHTML(item.evidence_id)}</strong></td>
          <td>
            <div style="font-weight: 600; color: #fff; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHTML(item.original_filename)}</div>
            <div style="font-size: 0.72rem; color: var(--text-dim);">${(item.file_size_bytes / 1024).toFixed(1)} KB</div>
          </td>
          <td><span class="badge badge-modality">${escapeHTML(item.modality)}</span></td>
          <td><span class="hash-mono">${escapeHTML((item.sha256_hash || '').substring(0, 12))}...</span></td>
          <td>${statusBadge}</td>
          <td>${riskBadge}</td>
          <td><span style="font-size: 0.8rem; color: var(--text-muted);">${item.findings_count || 0} signal(s)</span></td>
          <td>
            <button class="btn btn-primary" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;" onclick="openEvidenceInLab('${escapeHTML(item.evidence_id)}')">
              🔬 View in Lab
            </button>
          </td>
        </tr>
      `;
    }).join("");
  }
}

function downloadCurrentCaseReport() {
  if (!currentCaseId) return;
  window.open(`/api/reports/cases/${encodeURIComponent(currentCaseId)}/download`, '_blank');
}

function quickIngestToCurrentCase() {
  if (!currentCaseId) return;
  switchView("upload");
  const select = document.getElementById("upload-case-id");
  if (select) select.value = currentCaseId;
}

// 8. Generate Structured AI Forensic Explanation
async function generateAIExplanation() {
  if (!currentEvidenceId) return;

  const btn = document.getElementById("btn-ai-explain");
  const container = document.getElementById("ai-explanation-container");
  const origBtnText = btn ? btn.innerText : "⚡ Generate AI Explanation";

  if (btn) {
    btn.innerText = "⏳ Generating Synthesis...";
    btn.disabled = true;
  }

  try {
    const res = await fetch(`/api/evidence/${currentEvidenceId}/explain`, { method: "POST" });
    if (!res.ok) {
      alert("Failed to generate AI explanation. Please retry.");
      return;
    }
    const data = await res.json();

    document.getElementById("ai-expl-source-badge").innerText = data.source;
    document.getElementById("ai-expl-summary").innerText = data.investigator_summary;
    
    const findingsDiv = document.getElementById("ai-expl-findings");
    if (Array.isArray(data.technical_findings_requiring_review)) {
      findingsDiv.innerHTML = data.technical_findings_requiring_review.map(f => `• ${escapeHTML(f)}`).join("<br>");
    } else {
      findingsDiv.innerText = data.technical_findings_requiring_review;
    }

    document.getElementById("ai-expl-limitations").innerText = data.limitations;

    const stepsDiv = document.getElementById("ai-expl-steps");
    if (Array.isArray(data.recommended_next_steps)) {
      stepsDiv.innerHTML = data.recommended_next_steps.map(s => `• ${escapeHTML(s)}`).join("<br>");
    } else {
      stepsDiv.innerText = data.recommended_next_steps;
    }

    document.getElementById("ai-expl-disclaimer").innerText = data.disclaimer || "AI-assisted interpretation only. This does not determine authenticity, manipulation, or legal admissibility.";

    if (container) container.style.display = "block";
  } catch (err) {
    alert(`Error generating explanation: ${err}`);
  } finally {
    if (btn) {
      btn.innerText = origBtnText;
      btn.disabled = false;
    }
  }
}

