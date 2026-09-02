from __future__ import annotations

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


class AssessmentDraftUpdateRequest(AssessmentDraftFields):
    row_version: int = Field(ge=1)


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
    is_kev: bool


class AssessmentDetailResponse(BaseModel):
    assessment_id: int
    revision_no: int
    is_current: bool
    status: Literal["pending", "submitted", "returned", "completed", "reassess"]
    owner_id: int
    row_version: int
    editable: bool
    return_reason: str | None
    reassess_reason: str | None
    product: AssessmentProductResponse
    product_version: AssessmentProductVersionResponse
    ots: AssessmentOtsResponse
    vulnerability: AssessmentVulnerabilityResponse
    candidate: VulnerabilityCandidateResponse | None
    candidate_disclaimer: str
    draft: AssessmentDraftFields
