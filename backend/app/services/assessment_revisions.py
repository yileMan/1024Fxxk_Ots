from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.assessments import ProductAssessment
from app.repositories.assessment_editor import AssessmentEditorRepository
from app.services.automatic_reassessment import AssessmentBasis


DRAFT_FIELDS = (
    "analysis_summary",
    "trigger_conditions",
    "affected_functions",
    "applicability",
    "applicability_basis",
    "product_impact",
    "existing_controls",
    "treatment",
    "treatment_detail",
    "evidence_text",
)
SCORING_FIELDS = (
    "cvss_version",
    "environmental_score",
    "environmental_vector",
    "cvss_metrics_json",
    "calculator_version",
)
REVISION_COPY_FIELDS = (
    *DRAFT_FIELDS,
    *SCORING_FIELDS,
    "based_on_source_modified_at",
    "assessment_basis_sha256",
    "assessment_basis_json",
)
REVISION_EVENT_FIELDS = (
    "submitted_by",
    "submitted_at",
    "review_decision",
    "review_comment",
    "reviewer_id",
    "reviewed_at",
)
REVISION_SYSTEM_FIELDS = (
    "id",
    "product_ots_id",
    "vulnerability_id",
    "revision_no",
    "parent_revision_id",
    "is_current",
    "status",
    "owner_id",
    "reassess_reason",
    "reassess_changes_json",
    "row_version",
    "created_at",
    "updated_at",
)


def clone_assessment_revision(
    session: Session,
    repository: AssessmentEditorRepository,
    *,
    assessment: ProductAssessment,
    expected_status: str,
    row_version: int,
    parent_values: dict[str, object],
    child_status: str,
    owner_id: int,
    reassess_reason: str | None,
    reassess_changes_json: dict[str, object] | None,
    now: datetime,
    basis: AssessmentBasis | None = None,
) -> ProductAssessment | None:
    copied = {field: getattr(assessment, field) for field in REVISION_COPY_FIELDS}
    if basis is not None:
        copied.update(
            assessment_basis_sha256=basis.sha256,
            assessment_basis_json=basis.data,
        )
    if not repository.transition_if_version(
        session,
        assessment_id=assessment.id,
        expected_status=expected_status,
        row_version=row_version,
        values=parent_values,
        updated_at=now,
    ):
        return None
    child = ProductAssessment(
        product_ots_id=assessment.product_ots_id,
        vulnerability_id=assessment.vulnerability_id,
        revision_no=repository.next_revision_no(
            session,
            product_ots_id=assessment.product_ots_id,
            vulnerability_id=assessment.vulnerability_id,
        ),
        parent_revision_id=assessment.id,
        is_current=True,
        status=child_status,
        owner_id=owner_id,
        **copied,
        **{field: None for field in REVISION_EVENT_FIELDS},
        reassess_reason=reassess_reason,
        reassess_changes_json=reassess_changes_json,
        row_version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(child)
    session.flush()
    return child
