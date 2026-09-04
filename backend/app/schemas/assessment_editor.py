from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.vulnerability_catalog import VulnerabilityCandidateResponse


Applicability = Literal["affected", "not_affected", "partly_affected", "pending"]
Treatment = Literal[
    "patch_or_upgrade",
    "configuration_mitigation",
    "isolation_or_compensating_control",
    "accept_risk",
    "no_action",
    "further_investigation",
]


class Cvss31EnvironmentalMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    CR: Literal["X", "L", "M", "H"] = "X"
    IR: Literal["X", "L", "M", "H"] = "X"
    AR: Literal["X", "L", "M", "H"] = "X"
    MAV: Literal["X", "N", "A", "L", "P"] = "X"
    MAC: Literal["X", "L", "H"] = "X"
    MPR: Literal["X", "N", "L", "H"] = "X"
    MUI: Literal["X", "N", "R"] = "X"
    MS: Literal["X", "U", "C"] = "X"
    MC: Literal["X", "N", "L", "H"] = "X"
    MI: Literal["X", "N", "L", "H"] = "X"
    MA: Literal["X", "N", "L", "H"] = "X"


class AssessmentDraftFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_summary: str | None = Field(None, max_length=10_000)
    trigger_conditions: str | None = Field(None, max_length=10_000)
    affected_functions: str | None = Field(None, max_length=10_000)
    applicability: Applicability
    applicability_basis: str | None = Field(None, max_length=10_000)
    product_impact: str | None = Field(None, max_length=10_000)
    existing_controls: str | None = Field(None, max_length=10_000)
    treatment: Treatment | None = None
    treatment_detail: str | None = Field(None, max_length=10_000)
    evidence_text: str | None = Field(None, max_length=10_000)
    cvss_metrics: Cvss31EnvironmentalMetrics | None = None


class AssessmentDraftUpdateRequest(AssessmentDraftFields):
    row_version: int = Field(ge=1)


class AssessmentActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)


class AssessmentReturnRequest(AssessmentActionRequest):
    review_comment: str = Field(min_length=1, max_length=10_000)


class AssessmentRevisionCreateRequest(AssessmentActionRequest):
    revision_reason: str = Field(min_length=1, max_length=500)


class AssessmentProductResponse(BaseModel):
    id: int
    name: str


class AssessmentProductVersionResponse(BaseModel):
    id: int
    version_no: str


class AssessmentOtsResponse(BaseModel):
    id: int
    name: str
    version: str


class AssessmentVulnerabilityResponse(BaseModel):
    id: int
    cve_id: str
    source_status: str
    description: str | None
    cvss31_score: float | None
    cvss31_severity: str | None
    cvss31_vector: str | None
    cvss31_source: str | None
    is_kev: bool


class EnvironmentalScoringResponse(BaseModel):
    available: bool
    unavailable_reason: Literal["SOURCE_NOT_PROVIDED", "SOURCE_VECTOR_INVALID"] | None
    metrics: Cvss31EnvironmentalMetrics | None
    score: float | None
    vector: str | None
    calculator_version: str | None


class AssessmentActionsResponse(BaseModel):
    can_submit: bool
    can_approve: bool
    can_return: bool
    can_create_revision: bool
    unavailable_reason: str | None


class ReassessmentChangeResponse(BaseModel):
    field: str
    before: object | None
    after: object | None


class ReassessmentResponse(BaseModel):
    trigger_type: str
    triggered_at: datetime
    basis_sha256: str
    change_types: list[str]
    changes: list[ReassessmentChangeResponse]
    truncated_count: int


class AssessmentDetailResponse(BaseModel):
    assessment_id: int
    revision_no: int
    parent_revision_id: int | None
    current_revision_id: int
    is_current: bool
    status: Literal["pending", "submitted", "returned", "completed", "reassess"]
    owner_id: int
    row_version: int
    editable: bool
    submitted_by: int | None
    submitted_at: datetime | None
    review_decision: Literal["approved", "returned"] | None
    review_comment: str | None
    reviewer_id: int | None
    reviewed_at: datetime | None
    actions: AssessmentActionsResponse
    return_reason: str | None
    reassess_reason: str | None
    reason_type: Literal["review_return", "manual_revision", "automatic_reassessment"] | None
    reassessment: ReassessmentResponse | None = None
    product: AssessmentProductResponse
    product_version: AssessmentProductVersionResponse
    ots: AssessmentOtsResponse
    vulnerability: AssessmentVulnerabilityResponse
    candidate: VulnerabilityCandidateResponse | None
    candidate_disclaimer: str
    draft: AssessmentDraftFields
    environmental_scoring: EnvironmentalScoringResponse


class AssessmentReviewedRevisionResponse(BaseModel):
    assessment_id: int
    revision_no: int
    status: Literal["returned"]
    review_decision: Literal["returned"]
    review_comment: str
    reviewer_id: int
    reviewed_at: datetime


class AssessmentReturnResponse(BaseModel):
    current_revision: AssessmentDetailResponse
    reviewed_revision: AssessmentReviewedRevisionResponse


class AssessmentRevisionSummaryResponse(BaseModel):
    assessment_id: int
    revision_no: int
    parent_revision_id: int | None
    is_current: bool
    status: Literal["pending", "submitted", "returned", "completed", "reassess"]
    owner_id: int
    submitted_by: int | None
    submitted_at: datetime | None
    review_decision: Literal["approved", "returned"] | None
    review_comment: str | None
    reviewer_id: int | None
    reviewed_at: datetime | None
    return_reason: str | None
    reassess_reason: str | None
    reason_type: Literal["review_return", "manual_revision", "automatic_reassessment"] | None
    reassessment: ReassessmentResponse | None = None
    created_at: datetime
    updated_at: datetime


class AssessmentRevisionHistoryResponse(BaseModel):
    items: list[AssessmentRevisionSummaryResponse]


class AssessmentRevisionChangeResponse(BaseModel):
    field: str
    category: Literal["business", "event"]
    before: object | None
    after: object | None


class AssessmentRevisionComparisonResponse(BaseModel):
    base_revision_id: int
    target_revision_id: int
    changes: list[AssessmentRevisionChangeResponse]
