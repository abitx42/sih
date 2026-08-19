from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

# --- Cases ---
class CaseCreate(BaseModel):
    case_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    lead_investigator: str = "Lead Forensic Analyst"

class CaseResponse(BaseModel):
    case_id: str
    title: str
    description: Optional[str]
    lead_investigator: str
    created_at: str
    status: str
    evidence_count: Optional[int] = 0

# --- Evidence ---
class EvidenceBase(BaseModel):
    evidence_id: str
    case_id: str
    original_filename: str
    modality: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    sha512_hash: str
    md5_hash: str
    uploaded_by: str
    uploaded_at: str
    status: str
    pipeline_status: Optional[str] = "COMPLETED"
    analysis_started_at: Optional[str] = None
    analyzed_at: Optional[str] = None
    error_message: Optional[str] = None
    notes: Optional[str] = None

class EvidenceStatusResponse(BaseModel):
    evidence_id: str
    status: str
    pipeline_status: str
    modality: str
    original_filename: str
    uploaded_at: str
    analysis_started_at: Optional[str] = None
    analyzed_at: Optional[str] = None
    error_message: Optional[str] = None

class EvidenceListResponse(BaseModel):
    items: List[EvidenceBase]
    total: int

# --- Findings ---
class FindingSchema(BaseModel):
    finding_id: str
    evidence_id: str
    signal_name: str
    category: str  # INTEGRITY, METADATA, AI_DETECTION, SIGNAL_ANALYSIS, PROVENANCE
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    score: float
    explanation: str
    location_ref: Optional[str] = None
    created_at: str

# --- Forensic Results ---
class ForensicResultResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    result_id: str
    evidence_id: str
    integrity_status: str
    provenance_status: str
    ai_manipulation_score: Optional[float] = None
    ai_manipulation_indicator: Optional[float] = None
    ai_model_name: Optional[str] = None
    ai_model_version: Optional[str] = None
    model_confidence: Optional[float] = None
    model_status: str = "AVAILABLE"
    forensic_anomaly_score: float = 0.0
    forensic_risk_score: float
    risk_category: str
    confidence_score: float
    analyzed_at: str
    raw_metrics_json: Dict[str, Any]
    summary_narrative: Optional[str]
    recommendations: Optional[str]
    findings: List[FindingSchema] = []

# --- Complete Evidence Detail ---
class EvidenceDetailResponse(BaseModel):
    evidence: EvidenceBase
    case: Optional[CaseResponse] = None
    forensic_result: Optional[ForensicResultResponse] = None
    findings: List[FindingSchema] = []
    chain_of_custody: List[Dict[str, Any]] = []

# --- Chain of Custody ---
class CustodyEventResponse(BaseModel):
    event_id: str
    evidence_id: str
    action: str
    actor: str
    recorded_sha256: str
    details: str
    timestamp: str

# --- Integrity Verification ---
class IntegrityVerificationRequest(BaseModel):
    expected_sha256: Optional[str] = None

class IntegrityVerificationResponse(BaseModel):
    evidence_id: str
    recorded_sha256: str
    current_sha256: str
    is_valid: bool
    status: str
    verified_at: str
    details: str

# --- Copilot / AI Assistant ---
class CopilotQueryRequest(BaseModel):
    evidence_id: str
    question: str

class CopilotQueryResponse(BaseModel):
    evidence_id: str
    question: str
    answer: str
    source: str
    timestamp: str

class AIExplanationResponse(BaseModel):
    evidence_id: str
    investigator_summary: str
    technical_findings_requiring_review: Union[List[str], str]
    limitations: str
    recommended_next_steps: Union[List[str], str]
    disclaimer: str = "AI-assisted interpretation only. This does not determine authenticity, manipulation, or legal admissibility."
    source: str
    timestamp: str

# --- Dashboard Stats ---
class DashboardStatsResponse(BaseModel):
    total_cases: int
    total_evidence: int
    risk_distribution: Dict[str, int]
    modality_distribution: Dict[str, int]
    recent_evidence: List[EvidenceBase]
    recent_custody_events: List[CustodyEventResponse]
