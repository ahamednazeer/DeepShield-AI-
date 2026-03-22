from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AppBaseModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class RegisterRequest(AppBaseModel):
    username: str
    email: str
    password: str


class LoginRequest(AppBaseModel):
    username: str
    password: str


class TokenResponse(AppBaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(AppBaseModel):
    id: int
    username: str
    email: str
    role: str
    status: str = "active"
    created_at: str


class PermissionState(AppBaseModel):
    can_view: bool = True
    can_download: bool = True
    can_share: bool = True
    blocked_reason: Optional[str] = None


class ModerationState(AppBaseModel):
    is_flagged: bool = False
    is_quarantined: bool = False
    review_status: str = "clear"
    manual_verdict: Optional[str] = None
    review_notes: Optional[str] = None
    auto_actions: List[str] = Field(default_factory=list)
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None


class AnalysisResponse(AppBaseModel):
    id: int
    user_id: int
    filename: str
    original_filename: str
    media_type: str
    file_size: int
    status: str
    overall_score: Optional[float] = None
    verdict: Optional[str] = None
    raw_verdict: Optional[str] = None
    effective_verdict: Optional[str] = None
    image_score: Optional[float] = None
    video_score: Optional[float] = None
    audio_score: Optional[float] = None
    processing_time: Optional[float] = None
    selected_model: Optional[str] = None
    model_version: Optional[str] = None
    frames_total: Optional[int] = None
    frames_processed: Optional[int] = None
    progress_percent: Optional[float] = None
    created_at: str
    completed_at: Optional[str] = None
    evidence: Optional[List[dict]] = None
    permissions: Optional[PermissionState] = None
    moderation: Optional[ModerationState] = None


class AnalysisHistoryResponse(AppBaseModel):
    analyses: List[AnalysisResponse]
    total: int


class DashboardStats(AppBaseModel):
    total_analyses: int
    deepfake_count: int
    authentic_count: int
    suspicious_count: int
    avg_confidence: float
    recent_analyses: List[AnalysisResponse]
    media_type_distribution: dict
    verdict_distribution: dict
    total_media_analyses: int = 0
    total_text_analyses: int = 0
    total_link_analyses: int = 0
    total_content: int = 0
    flagged_content: int = 0
    pending_review: int = 0
    unread_notifications: int = 0
    content_type_distribution: dict = Field(default_factory=dict)
    recent_items: List[dict] = Field(default_factory=list)


class EvidenceItem(AppBaseModel):
    id: int
    analysis_id: int
    evidence_type: str
    title: str
    description: Optional[str] = None
    severity: str
    data: Optional[str] = None
    file_path: Optional[str] = None
    created_at: str


class TextAnalysisRequest(AppBaseModel):
    text: str
    source_url: Optional[str] = None


class LinkAnalysisRequest(AppBaseModel):
    url: str


class ClaimResult(AppBaseModel):
    text: str
    type: str
    confidence: float
    original: str


class EvidenceResult(AppBaseModel):
    type: str
    source: str
    title: str
    url: Optional[str] = None
    extract: Optional[str] = None


class TextAnalysisResponse(AppBaseModel):
    id: int
    user_id: int
    input_text: str
    source_url: Optional[str] = None
    status: str
    nlp_score: Optional[float] = None
    fact_score: Optional[float] = None
    credibility_score: Optional[float] = None
    final_score: Optional[float] = None
    verdict: Optional[str] = None
    raw_verdict: Optional[str] = None
    effective_verdict: Optional[str] = None
    verdict_label: Optional[str] = None
    claims: Optional[List[dict]] = None
    evidence: Optional[List[dict]] = None
    explanation: Optional[dict] = None
    semantic_results: Optional[List[dict]] = None
    claim_context: Optional[dict] = None
    llm_fact_check: Optional[dict] = None
    processing_time: Optional[float] = None
    created_at: str
    completed_at: Optional[str] = None
    permissions: Optional[PermissionState] = None
    moderation: Optional[ModerationState] = None


class TextAnalysisHistoryResponse(AppBaseModel):
    analyses: List[TextAnalysisResponse]
    total: int


class LinkAnalysisResponse(AppBaseModel):
    id: int
    user_id: int
    input_url: str
    normalized_url: Optional[str] = None
    final_url: Optional[str] = None
    domain: Optional[str] = None
    status: str
    risk_score: Optional[float] = None
    verdict: Optional[str] = None
    raw_verdict: Optional[str] = None
    effective_verdict: Optional[str] = None
    signals: List[dict] = Field(default_factory=list)
    provider_summary: dict = Field(default_factory=dict)
    redirect_chain: List[str] = Field(default_factory=list)
    page_metadata: dict = Field(default_factory=dict)
    processing_time: Optional[float] = None
    created_at: str
    completed_at: Optional[str] = None
    permissions: Optional[PermissionState] = None
    moderation: Optional[ModerationState] = None


class LinkAnalysisHistoryResponse(AppBaseModel):
    analyses: List[LinkAnalysisResponse]
    total: int


class AnalysisStartRequest(AppBaseModel):
    selected_model: Optional[str] = None


class MediaModelOption(AppBaseModel):
    id: str
    label: str
    description: Optional[str] = None
    available: bool = True
    recommended: bool = False
    experimental: bool = False
    backend: Optional[str] = None
    resolved_default: Optional[str] = None
    filename: Optional[str] = None


class MediaModelCatalogResponse(AppBaseModel):
    media_type: str
    models: List[MediaModelOption]
