from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.assessments import ProductAssessment
from app.services.audit import record_audit
from app.repositories.assessment_editor import EDITABLE_STATUSES, AssessmentEditorRepository
from app.repositories.vulnerability_catalog import VulnerabilityCatalogRepository
from app.schemas.assessment_editor import (
    AssessmentActionRequest,
    AssessmentDraftUpdateRequest,
    AssessmentRevisionCreateRequest,
    AssessmentReturnRequest,
)
from app.services.authentication import PublicUser
from app.services.cvss31 import Cvss31Error, calculate_environmental, parse_base_vector
from app.services.assessment_revisions import (
    DRAFT_FIELDS,
    REVISION_COPY_FIELDS,
    REVISION_EVENT_FIELDS,
    REVISION_SYSTEM_FIELDS,
    SCORING_FIELDS,
    clone_assessment_revision,
)
from app.services.vulnerability_matching import CANDIDATE_DISCLAIMER


TEXT_FIELDS = set(DRAFT_FIELDS) - {"applicability", "treatment"}
COMPARISON_BUSINESS_FIELDS = (*DRAFT_FIELDS, *SCORING_FIELDS)
COMPARISON_EVENT_FIELDS = (
    "status", "owner_id", "submitted_by", "submitted_at", "review_decision",
    "review_comment", "reviewer_id", "reviewed_at", "reassess_reason",
)


class AssessmentEditorError(Exception):
    code = "ASSESSMENT_EDITOR_ERROR"


class AssessmentNotFoundError(AssessmentEditorError):
    code = "ASSESSMENT_NOT_FOUND"


class AssessmentForbiddenError(AssessmentEditorError):
    code = "ASSESSMENT_FORBIDDEN"


class AssessmentNotEditableError(AssessmentEditorError):
    code = "ASSESSMENT_NOT_EDITABLE"

    def __init__(self, current_revision_id: int | None = None) -> None:
        self.current_revision_id = current_revision_id


class AssessmentVersionConflictError(AssessmentEditorError):
    code = "ASSESSMENT_VERSION_CONFLICT"


class AssessmentValidationError(AssessmentEditorError):
    code = "ASSESSMENT_VALIDATION_ERROR"

    def __init__(self, field: str, message: str = "此字段为必填项") -> None:
        self.fields = [{"path": field, "message": message}]


class AssessmentSubmitIncompleteError(AssessmentValidationError):
    code = "ASSESSMENT_SUBMIT_INCOMPLETE"

    def __init__(self, fields: list[str]) -> None:
        self.fields = [{"path": field, "message": "提交前必须填写完整"} for field in fields]


class CvssSourceUnavailableError(AssessmentValidationError):
    code = "CVSS31_SOURCE_UNAVAILABLE"


class AssessmentActionConflictError(AssessmentEditorError):
    code = "ASSESSMENT_ACTION_CONFLICT"


class ReviewerReassignmentRequiredError(AssessmentEditorError):
    code = "REVIEWER_REASSIGNMENT_REQUIRED"


class AssessmentSelfReviewError(AssessmentForbiddenError):
    code = "ASSESSMENT_SELF_REVIEW_FORBIDDEN"


class AssessmentEditorService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._repository = AssessmentEditorRepository()
        self._catalog = VulnerabilityCatalogRepository()

    @staticmethod
    def _is_admin(user: PublicUser) -> bool:
        return "admin" in user.roles

    def detail(self, user: PublicUser, assessment_id: int) -> dict[str, object]:
        with self._session_factory() as session:
            return self._detail(session, user, assessment_id)

    def approved_references(
        self, user: PublicUser, assessment_id: int
    ) -> list[dict[str, object]]:
        with self._session_factory() as session:
            context = self._visible_context(session, user, assessment_id)
            return self._repository.list_approved_references(
                session,
                product_id=int(context["product_id"]),
                ots_component_id=int(context["ots_component_id"]),
                vulnerability_id=int(context["vulnerability_id"]),
            )

    def save_draft(
        self,
        user: PublicUser,
        assessment_id: int,
        request: AssessmentDraftUpdateRequest,
    ) -> dict[str, object]:
        values = self._normalize(request)
        self._validate(values)
        with self._session_factory.begin() as session:
            context = self._visible_context(session, user, assessment_id)
            assessment = context["ProductAssessment"]
            assert isinstance(assessment, ProductAssessment)
            if (
                assessment.owner_id != user.id
                or int(context["version_owner_id"]) != user.id
            ):
                raise AssessmentForbiddenError()
            if not assessment.is_current or assessment.status not in EDITABLE_STATUSES:
                raise AssessmentNotEditableError(
                    self._repository.current_revision_id(
                        session,
                        product_ots_id=assessment.product_ots_id,
                        vulnerability_id=assessment.vulnerability_id,
                    )
                )
            if assessment.row_version != request.row_version:
                raise AssessmentVersionConflictError()

            metrics = values.pop("cvss_metrics")
            if metrics is not None:
                source_vector = context["cvss31_vector"]
                if not source_vector:
                    raise CvssSourceUnavailableError("cvss_metrics", "来源未提供 CVSS v3.1")
                try:
                    result = calculate_environmental(str(source_vector), metrics)
                except Cvss31Error as error:
                    raise CvssSourceUnavailableError(
                        "cvss_metrics", "来源 CVSS v3.1 向量无效"
                    ) from error
                values.update(
                    cvss_version="3.1",
                    environmental_score=result.score,
                    environmental_vector=result.vector,
                    cvss_metrics_json=result.metrics,
                    calculator_version=result.calculator_version,
                )

            changes = {
                field: (getattr(assessment, field), values[field])
                for field in (*DRAFT_FIELDS, *SCORING_FIELDS)
                if field in values
                if not self._values_equal(field, getattr(assessment, field), values[field])
            }
            if not changes:
                return self._serialize(session, user, context)

            updated = self._repository.update_draft_if_version(
                session,
                assessment_id=assessment_id,
                owner_id=user.id,
                row_version=request.row_version,
                values=values,
                updated_at=datetime.now(timezone.utc),
            )
            if not updated:
                session.expire_all()
                latest = self._repository.get_context(session, assessment_id)
                latest_assessment = latest["ProductAssessment"] if latest else None
                if (
                    isinstance(latest_assessment, ProductAssessment)
                    and latest_assessment.row_version != request.row_version
                ):
                    raise AssessmentVersionConflictError()
                raise AssessmentNotEditableError()

            record_audit(
                session, user_id=user.id, action="update",
                object_type="product_assessment", object_id=assessment_id,
                detail=self._audit_detail(
                    assessment.revision_no, request.row_version, changes
                ),
            )
            session.flush()
            session.expire_all()
            refreshed = self._repository.get_context(session, assessment_id)
            assert refreshed is not None
            return self._serialize(session, user, refreshed)

    def submit(
        self, user: PublicUser, assessment_id: int, request: AssessmentActionRequest
    ) -> dict[str, object]:
        with self._session_factory.begin() as session:
            context = self._visible_context(session, user, assessment_id)
            context = self._repository.get_context_for_update(session, assessment_id)
            assert context is not None
            assessment = self._assessment(context)
            if "product_owner" not in user.roles or assessment.owner_id != user.id or int(context["version_owner_id"]) != user.id:
                raise AssessmentForbiddenError()
            self._require_action_state(
                assessment, {"pending", "returned", "reassess"}, request.row_version
            )
            if int(context["version_reviewer_id"]) == user.id:
                raise ReviewerReassignmentRequiredError()
            missing = [
                field for field in DRAFT_FIELDS
                if field == "applicability" and assessment.applicability == "pending"
                or field != "applicability" and self._blank(getattr(assessment, field))
            ]
            if missing:
                raise AssessmentSubmitIncompleteError(missing)
            self._validate_persisted_scoring(assessment, context)
            now = datetime.now(timezone.utc)
            expected_status = assessment.status
            self._transition(
                session, assessment, request.row_version, expected_status,
                {"status": "submitted", "submitted_by": user.id, "submitted_at": now},
                now, "submit" if expected_status == "pending" else "resubmit", user.id,
            )
            return self._refreshed_detail(session, user, assessment_id)

    def approve(
        self, user: PublicUser, assessment_id: int, request: AssessmentActionRequest
    ) -> dict[str, object]:
        return self._review(user, assessment_id, request.row_version, "approved", None)

    def return_assessment(
        self, user: PublicUser, assessment_id: int, request: AssessmentReturnRequest
    ) -> dict[str, object]:
        comment = request.review_comment.strip()
        if not comment:
            raise AssessmentValidationError("review_comment")
        with self._session_factory.begin() as session:
            context = self._visible_context(session, user, assessment_id)
            context = self._repository.get_context_for_update(session, assessment_id)
            assert context is not None
            assessment = self._assessment(context)
            if "reviewer" not in user.roles or int(context["version_reviewer_id"]) != user.id:
                raise AssessmentForbiddenError()
            if assessment.submitted_by == user.id:
                raise AssessmentSelfReviewError()
            self._require_action_state(assessment, "submitted", request.row_version)
            now = datetime.now(timezone.utc)
            child = self._create_child_revision(
                session,
                assessment=assessment,
                expected_status="submitted",
                row_version=request.row_version,
                parent_values={
                    "status": "returned",
                    "is_current": False,
                    "review_decision": "returned",
                    "review_comment": comment,
                    "reviewer_id": user.id,
                    "reviewed_at": now,
                },
                child_status="returned",
                reassess_reason=None,
                actor_id=user.id,
                action="return_create_revision",
                now=now,
            )
            current = self._refreshed_detail(session, user, child.id)
            session.expire_all()
            reviewed = session.get(ProductAssessment, assessment_id)
            assert reviewed is not None
            return {
                "current_revision": current,
                "reviewed_revision": {
                    "assessment_id": reviewed.id,
                    "revision_no": reviewed.revision_no,
                    "status": reviewed.status,
                    "review_decision": reviewed.review_decision,
                    "review_comment": reviewed.review_comment,
                    "reviewer_id": reviewed.reviewer_id,
                    "reviewed_at": reviewed.reviewed_at,
                },
            }

    def create_revision(
        self,
        user: PublicUser,
        assessment_id: int,
        request: AssessmentRevisionCreateRequest,
    ) -> dict[str, object]:
        reason = request.revision_reason.strip()
        if not reason:
            raise AssessmentValidationError("revision_reason")
        with self._session_factory.begin() as session:
            context = self._visible_context(session, user, assessment_id)
            context = self._repository.get_context_for_update(session, assessment_id)
            assert context is not None
            assessment = self._assessment(context)
            if (
                "product_owner" not in user.roles
                or assessment.owner_id != user.id
                or int(context["version_owner_id"]) != user.id
            ):
                raise AssessmentForbiddenError()
            self._require_action_state(assessment, "completed", request.row_version)
            now = datetime.now(timezone.utc)
            child = self._create_child_revision(
                session,
                assessment=assessment,
                expected_status="completed",
                row_version=request.row_version,
                parent_values={"is_current": False},
                child_status="reassess",
                reassess_reason=reason,
                actor_id=user.id,
                action="manual_create_revision",
                now=now,
            )
            return self._refreshed_detail(session, user, child.id)

    def revision_history(
        self, user: PublicUser, assessment_id: int
    ) -> dict[str, object]:
        with self._session_factory() as session:
            context = self._visible_context(session, user, assessment_id)
            assessment = self._assessment(context)
            revisions = self._repository.list_revisions(
                session,
                product_ots_id=assessment.product_ots_id,
                vulnerability_id=assessment.vulnerability_id,
            )
            return {
                "items": [self._serialize_revision_summary(session, item) for item in revisions]
            }

    def compare_revisions(
        self,
        user: PublicUser,
        assessment_id: int,
        base_revision_id: int,
        target_revision_id: int,
    ) -> dict[str, object]:
        with self._session_factory() as session:
            anchor = self._assessment(self._visible_context(session, user, assessment_id))
            base = self._assessment(self._visible_context(session, user, base_revision_id))
            target = self._assessment(self._visible_context(session, user, target_revision_id))
            chain = (anchor.product_ots_id, anchor.vulnerability_id)
            if (
                (base.product_ots_id, base.vulnerability_id) != chain
                or (target.product_ots_id, target.vulnerability_id) != chain
            ):
                raise AssessmentValidationError(
                    "target_revision_id", "修订不属于同一评估链"
                )
            changes = []
            for category, fields in (
                ("business", COMPARISON_BUSINESS_FIELDS),
                ("event", COMPARISON_EVENT_FIELDS),
            ):
                for field in fields:
                    before = getattr(base, field)
                    after = getattr(target, field)
                    if not self._values_equal(field, before, after):
                        changes.append({
                            "field": field,
                            "category": category,
                            "before": before,
                            "after": after,
                        })
            return {
                "base_revision_id": base.id,
                "target_revision_id": target.id,
                "changes": changes,
            }

    def _review(
        self, user: PublicUser, assessment_id: int, row_version: int,
        decision: str, comment: str | None,
    ) -> dict[str, object]:
        with self._session_factory.begin() as session:
            context = self._visible_context(session, user, assessment_id)
            assessment = self._assessment(context)
            if "reviewer" not in user.roles or int(context["version_reviewer_id"]) != user.id:
                raise AssessmentForbiddenError()
            if assessment.submitted_by == user.id:
                raise AssessmentSelfReviewError()
            self._require_action_state(assessment, "submitted", row_version)
            now = datetime.now(timezone.utc)
            target_status = "completed" if decision == "approved" else "returned"
            self._transition(
                session, assessment, row_version, "submitted",
                {
                    "status": target_status,
                    "review_decision": decision,
                    "review_comment": comment,
                    "reviewer_id": user.id,
                    "reviewed_at": now,
                },
                now, "approve" if decision == "approved" else "return", user.id,
            )
            return self._refreshed_detail(session, user, assessment_id)

    @staticmethod
    def _assessment(context: dict[str, object]) -> ProductAssessment:
        assessment = context["ProductAssessment"]
        assert isinstance(assessment, ProductAssessment)
        return assessment

    @staticmethod
    def _blank(value: object) -> bool:
        return value is None or isinstance(value, str) and not value.strip()

    @staticmethod
    def _require_action_state(
        assessment: ProductAssessment,
        expected_status: str | set[str],
        row_version: int,
    ) -> None:
        statuses = {expected_status} if isinstance(expected_status, str) else expected_status
        if not assessment.is_current or assessment.status not in statuses:
            raise AssessmentActionConflictError()
        if assessment.row_version != row_version:
            raise AssessmentVersionConflictError()

    @staticmethod
    def _validate_persisted_scoring(
        assessment: ProductAssessment, context: dict[str, object]
    ) -> None:
        source_vector = context["cvss31_vector"]
        if not source_vector:
            return
        try:
            parse_base_vector(str(source_vector))
            if assessment.cvss_metrics_json is None:
                return
            result = calculate_environmental(str(source_vector), assessment.cvss_metrics_json)
        except Cvss31Error as error:
            raise AssessmentActionConflictError() from error
        if (
            assessment.cvss_version != "3.1"
            or assessment.environmental_score is None
            or Decimal(str(assessment.environmental_score)) != Decimal(str(result.score))
            or assessment.environmental_vector != result.vector
            or assessment.calculator_version != result.calculator_version
        ):
            raise AssessmentActionConflictError()

    def _transition(
        self, session: Session, assessment: ProductAssessment, row_version: int,
        expected_status: str, values: dict[str, object], now: datetime,
        action: str, actor_id: int,
    ) -> None:
        if not self._repository.transition_if_version(
            session, assessment_id=assessment.id, expected_status=expected_status,
            row_version=row_version, values=values, updated_at=now,
        ):
            raise AssessmentActionConflictError()
        record_audit(
            session, user_id=actor_id, action="update",
            object_type="product_assessment", object_id=assessment.id,
            detail={
                "action": action,
                "revision_no": assessment.revision_no,
                "status": {"from": expected_status, "to": values["status"]},
                "row_version": {"from": row_version, "to": row_version + 1},
            },
        )
        session.flush()

    def _create_child_revision(
        self,
        session: Session,
        *,
        assessment: ProductAssessment,
        expected_status: str,
        row_version: int,
        parent_values: dict[str, object],
        child_status: str,
        reassess_reason: str | None,
        actor_id: int,
        action: str,
        now: datetime,
    ) -> ProductAssessment:
        changes = {
            "trigger_type": "manual_revision",
            "triggered_at": now.isoformat().replace("+00:00", "Z"),
            "change_types": [],
            "changes": [],
            "truncated_count": 0,
        } if action == "manual_create_revision" else None
        child = clone_assessment_revision(
            session,
            self._repository,
            assessment=assessment,
            expected_status=expected_status,
            row_version=row_version,
            parent_values=parent_values,
            child_status=child_status,
            owner_id=assessment.owner_id,
            reassess_reason=reassess_reason,
            reassess_changes_json=changes,
            now=now,
        )
        if child is None:
            raise AssessmentActionConflictError()
        record_audit(
            session, user_id=actor_id, action="update",
            object_type="product_assessment", object_id=assessment.id,
            detail={
                "action": action,
                "parent_assessment_id": assessment.id,
                "parent_revision_no": assessment.revision_no,
                "child_assessment_id": child.id,
                "child_revision_no": child.revision_no,
                "status": {"from": expected_status, "to": child_status},
                "current": {"parent": False, "child": True},
            },
        )
        session.flush()
        return child

    def _refreshed_detail(
        self, session: Session, user: PublicUser, assessment_id: int
    ) -> dict[str, object]:
        session.expire_all()
        context = self._repository.get_context(session, assessment_id)
        assert context is not None
        return self._serialize(session, user, context)

    def _visible_context(
        self, session: Session, user: PublicUser, assessment_id: int
    ) -> dict[str, object]:
        context = self._repository.get_context(session, assessment_id)
        if context is None:
            raise AssessmentNotFoundError()
        if not self._is_admin(user):
            version_ids = self._repository.effective_version_ids(session, user.id)
            if int(context["product_version_id"]) not in version_ids:
                raise AssessmentForbiddenError()
        return context

    def _detail(
        self, session: Session, user: PublicUser, assessment_id: int
    ) -> dict[str, object]:
        return self._serialize(session, user, self._visible_context(session, user, assessment_id))

    def _serialize(
        self, session: Session, user: PublicUser, context: dict[str, object]
    ) -> dict[str, object]:
        assessment = context["ProductAssessment"]
        assert isinstance(assessment, ProductAssessment)
        current_revision_id = self._repository.current_revision_id(
            session,
            product_ots_id=assessment.product_ots_id,
            vulnerability_id=assessment.vulnerability_id,
        )
        assert current_revision_id is not None
        candidates = self._catalog.list_candidates(
            session,
            vulnerability_id=int(context["vulnerability_id"]),
            version_ids=None,
        )
        candidate = next(
            (
                item
                for item in candidates
                if int(item["ots_component_id"]) == int(context["ots_component_id"])
            ),
            None,
        )
        editable = (
            assessment.is_current
            and assessment.status in EDITABLE_STATUSES
            and assessment.owner_id == user.id
            and int(context["version_owner_id"]) == user.id
        )
        can_submit = (
            editable
            and assessment.status in {"pending", "returned", "reassess"}
            and "product_owner" in user.roles
            and int(context["version_owner_id"]) == user.id
            and int(context["version_reviewer_id"]) != user.id
        )
        can_review = (
            assessment.is_current
            and assessment.status == "submitted"
            and "reviewer" in user.roles
            and int(context["version_reviewer_id"]) == user.id
            and assessment.submitted_by != user.id
        )
        can_create_revision = (
            assessment.is_current
            and assessment.status == "completed"
            and "product_owner" in user.roles
            and assessment.owner_id == user.id
            and int(context["version_owner_id"]) == user.id
        )
        unavailable_reason = self._action_unavailable_reason(
            user, context, assessment, can_submit, can_review, can_create_revision
        )
        parent = session.get(ProductAssessment, assessment.parent_revision_id) \
            if assessment.parent_revision_id is not None else None
        return_reason = (
            parent.review_comment
            if assessment.status == "returned" and parent is not None
            else assessment.review_comment if assessment.status == "returned" else None
        )
        return {
            "assessment_id": assessment.id,
            "revision_no": assessment.revision_no,
            "parent_revision_id": assessment.parent_revision_id,
            "current_revision_id": current_revision_id,
            "is_current": assessment.is_current,
            "status": assessment.status,
            "owner_id": assessment.owner_id,
            "row_version": assessment.row_version,
            "editable": editable,
            "submitted_by": assessment.submitted_by,
            "submitted_at": assessment.submitted_at,
            "review_decision": assessment.review_decision,
            "review_comment": assessment.review_comment,
            "reviewer_id": assessment.reviewer_id,
            "reviewed_at": assessment.reviewed_at,
            "actions": {
                "can_submit": can_submit,
                "can_approve": can_review,
                "can_return": can_review,
                "can_create_revision": can_create_revision,
                "unavailable_reason": unavailable_reason,
            },
            "return_reason": return_reason,
            "reassess_reason": assessment.reassess_reason if assessment.status == "reassess" else None,
            "reason_type": self._reason_type(session, assessment),
            "reassessment": self._serialize_reassessment(assessment),
            "product": {"id": context["product_id"], "name": context["product_name"]},
            "product_version": {
                "id": context["product_version_id"],
                "version_no": context["version_no"],
            },
            "ots": {
                "id": context["ots_component_id"],
                "name": context["ots_name"],
                "version": context["ots_version"],
            },
            "vulnerability": {
                "id": context["vulnerability_id"],
                "cve_id": context["cve_id"],
                "source_status": context["source_status"],
                "description": context["description"],
                "cvss31_score": float(context["cvss31_score"])
                if context["cvss31_score"] is not None
                else None,
                "cvss31_severity": context["cvss31_severity"],
                "cvss31_vector": context["cvss31_vector"],
                "cvss31_source": context["cvss31_source"],
                "is_kev": context["is_kev"],
            },
            "candidate": candidate,
            "candidate_disclaimer": CANDIDATE_DISCLAIMER,
            "draft": {
                **{field: getattr(assessment, field) for field in DRAFT_FIELDS},
                "cvss_metrics": assessment.cvss_metrics_json,
            },
            "environmental_scoring": self._serialize_scoring(assessment, context),
        }

    @staticmethod
    def _action_unavailable_reason(
        user: PublicUser, context: dict[str, object], assessment: ProductAssessment,
        can_submit: bool, can_review: bool, can_create_revision: bool,
    ) -> str | None:
        if can_submit or can_review or can_create_revision:
            return None
        if not assessment.is_current:
            return None
        if assessment.status == "submitted":
            return "ASSESSMENT_ALREADY_SUBMITTED"
        if assessment.status == "returned":
            return "ACTION_NOT_ALLOWED"
        if assessment.status == "completed":
            return "ASSESSMENT_COMPLETED"
        if assessment.status == "reassess":
            return "ACTION_NOT_ALLOWED"
        if int(context["version_reviewer_id"]) == user.id and assessment.owner_id == user.id:
            return "REVIEWER_REASSIGNMENT_REQUIRED"
        return "ACTION_NOT_ALLOWED"

    @staticmethod
    def _reason_type(_session: Session, assessment: ProductAssessment) -> str | None:
        if assessment.status == "returned" and assessment.parent_revision_id is not None:
            return "review_return"
        if assessment.status != "reassess" or not assessment.reassess_reason:
            return None
        changes = assessment.reassess_changes_json
        if isinstance(changes, dict):
            trigger_type = changes.get("trigger_type")
            if trigger_type in {"automatic_reassessment", "manual_revision"}:
                return str(trigger_type)
        return "automatic_reassessment"

    def _serialize_revision_summary(
        self, session: Session, assessment: ProductAssessment
    ) -> dict[str, object]:
        parent = session.get(ProductAssessment, assessment.parent_revision_id) \
            if assessment.parent_revision_id is not None else None
        return {
            "assessment_id": assessment.id,
            "revision_no": assessment.revision_no,
            "parent_revision_id": assessment.parent_revision_id,
            "is_current": assessment.is_current,
            "status": assessment.status,
            "owner_id": assessment.owner_id,
            "submitted_by": assessment.submitted_by,
            "submitted_at": assessment.submitted_at,
            "review_decision": assessment.review_decision,
            "review_comment": assessment.review_comment,
            "reviewer_id": assessment.reviewer_id,
            "reviewed_at": assessment.reviewed_at,
            "return_reason": parent.review_comment
            if assessment.status == "returned" and parent is not None
            else assessment.review_comment if assessment.status == "returned" else None,
            "reassess_reason": assessment.reassess_reason,
            "reason_type": self._reason_type(session, assessment),
            "reassessment": self._serialize_reassessment(assessment),
            "created_at": assessment.created_at,
            "updated_at": assessment.updated_at,
        }

    @staticmethod
    def _serialize_reassessment(
        assessment: ProductAssessment,
    ) -> dict[str, object] | None:
        changes = assessment.reassess_changes_json
        if not isinstance(changes, dict) or not assessment.assessment_basis_sha256:
            return None
        return {
            "trigger_type": changes.get("trigger_type", "automatic_reassessment"),
            "triggered_at": changes.get("triggered_at"),
            "basis_sha256": assessment.assessment_basis_sha256,
            "change_types": changes.get("change_types", []),
            "changes": changes.get("changes", []),
            "truncated_count": changes.get("truncated_count", 0),
        }

    @staticmethod
    def _serialize_scoring(
        assessment: ProductAssessment, context: dict[str, object]
    ) -> dict[str, object]:
        source_vector = context["cvss31_vector"]
        unavailable_reason = None
        if not source_vector:
            unavailable_reason = "SOURCE_NOT_PROVIDED"
        else:
            try:
                parse_base_vector(str(source_vector))
            except Cvss31Error:
                unavailable_reason = "SOURCE_VECTOR_INVALID"
        return {
            "available": unavailable_reason is None,
            "unavailable_reason": unavailable_reason,
            "metrics": assessment.cvss_metrics_json,
            "score": float(assessment.environmental_score)
            if assessment.environmental_score is not None
            else None,
            "vector": assessment.environmental_vector,
            "calculator_version": assessment.calculator_version,
        }

    @staticmethod
    def _normalize(request: AssessmentDraftUpdateRequest) -> dict[str, object]:
        values = request.model_dump(exclude={"row_version"})
        for field in TEXT_FIELDS:
            value = values[field]
            if isinstance(value, str):
                values[field] = value.strip() or None
        metrics = values["cvss_metrics"]
        if metrics is not None:
            values["cvss_metrics"] = metrics
        return values

    @staticmethod
    def _validate(values: dict[str, object]) -> None:
        if values["applicability"] != "pending" and values["applicability_basis"] is None:
            raise AssessmentValidationError("applicability_basis")
        if values["treatment"] in {"accept_risk", "no_action"} and values["treatment_detail"] is None:
            raise AssessmentValidationError("treatment_detail")

    @classmethod
    def _audit_detail(
        cls,
        revision_no: int,
        row_version: int,
        changes: dict[str, tuple[object, object]],
    ) -> dict[str, object]:
        return {
            "revision_no": revision_no,
            "changed_fields": list(changes),
            "row_version": {"from": row_version, "to": row_version + 1},
            "changes": {
                field: {
                    "from": cls._audit_value(field, before),
                    "to": cls._audit_value(field, after),
                }
                for field, (before, after) in changes.items()
            },
        }

    @staticmethod
    def _audit_value(field: str, value: object) -> object:
        if field == "environmental_vector":
            text = value if isinstance(value, str) else ""
            return {
                "present": value is not None,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()
                if value is not None
                else None,
            }
        if field not in TEXT_FIELDS:
            return float(value) if isinstance(value, Decimal) else value
        text = value if isinstance(value, str) else ""
        return {
            "present": value is not None,
            "length": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()
            if value is not None
            else None,
        }

    @staticmethod
    def _values_equal(field: str, before: object, after: object) -> bool:
        if field == "environmental_score" and before is not None and after is not None:
            return Decimal(str(before)) == Decimal(str(after))
        return before == after
