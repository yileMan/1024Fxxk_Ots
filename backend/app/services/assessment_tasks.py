from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from sqlalchemy.orm import Session

from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability, VulnerabilityOtsMatch
from app.repositories.assessment_tasks import AssessmentTaskRepository, ProductOtsContext
from app.repositories.assessment_editor import AssessmentEditorRepository
from app.services.assessment_revisions import clone_assessment_revision
from app.services.automatic_reassessment import (
    AssessmentBasis,
    build_assessment_basis,
    diff_assessment_basis,
    merge_reassessment_changes,
)

if TYPE_CHECKING:
    from app.services.vulnerability_matching import CalculatedCandidate


PRODUCT_DISABLED = "PRODUCT_DISABLED"
PRODUCT_VERSION_DISABLED = "PRODUCT_VERSION_DISABLED"
OWNER_UNAVAILABLE = "OWNER_UNAVAILABLE"
NO_ACTIVE_PRODUCT_OTS = "NO_ACTIVE_PRODUCT_OTS"
ASSESSMENT_IN_PROGRESS = "ASSESSMENT_IN_PROGRESS"


@dataclass(frozen=True)
class TaskOperation:
    action: Literal["inserted", "updated", "reassess", "unchanged", "skipped"]
    vulnerability_id: int
    cve_id: str
    context: ProductOtsContext | None
    source_modified_at: datetime | None
    current: ProductAssessment | None = None
    reason: str | None = None
    basis: AssessmentBasis | None = None
    changes: dict[str, object] | None = None

    def sample(self) -> dict[str, object]:
        context = self.context
        return {
            "vulnerability_id": self.vulnerability_id,
            "cve_id": self.cve_id,
            "product_id": context.product_id if context else None,
            "product_name": context.product_name if context else None,
            "product_version_id": context.product_version_id if context else None,
            "version_no": context.version_no if context else None,
            "product_ots_id": context.product_ots_id if context else None,
            "owner_id": context.owner_id if context else None,
            "action": self.action,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TaskPlan:
    operations: tuple[TaskOperation, ...]
    result: dict[str, object]


class AssessmentTaskService:
    def __init__(self) -> None:
        self._repository = AssessmentTaskRepository()
        self._revision_repository = AssessmentEditorRepository()

    def plan_source_changes(
        self,
        session: Session,
        *,
        vulnerabilities: list[Vulnerability],
        status: str,
        lock: bool = False,
    ) -> TaskPlan:
        from app.services.vulnerability_matching import CalculatedCandidate

        candidates = self._repository.list_candidates(
            session, {item.id for item in vulnerabilities}
        )
        source_by_id = {item.id: item for item in vulnerabilities}
        targets = [
            CalculatedCandidate(
                vulnerability_id=item.vulnerability_id,
                cve_id=source_by_id[item.vulnerability_id].cve_id,
                ots_component_id=item.ots_component_id,
                ots_name="",
                ots_version="",
                match_method=item.match_method,
                match_basis=item.match_basis,
                evidence=item.match_evidence_json or {},
                content_sha256=item.match_content_sha256,
                source_modified_at=source_by_id[item.vulnerability_id].source_modified_at,
            )
            for item in candidates
            if item.vulnerability_id in source_by_id
        ]
        return self.plan(
            session,
            vulnerabilities=vulnerabilities,
            targets=targets,
            existing_candidates=candidates,
            status=status,
            lock=lock,
        )

    def plan_relation_change(
        self,
        session: Session,
        *,
        product_ots_id: int,
        target_status: str,
        status: str,
        lock: bool = False,
    ) -> TaskPlan:
        context = self._repository.get_product_context(session, product_ots_id)
        if context is None:
            raise RuntimeError("product OTS context not found")
        operations: list[TaskOperation] = []
        for current, vulnerability, candidate in self._repository.list_relation_current_facts(
            session, product_ots_id, lock=lock
        ):
            basis = build_assessment_basis(
                source=vulnerability,
                candidate=candidate,
                product_ots_id=product_ots_id,
                product_ots_status=target_status,
                kev_available=False,
            )
            changes = self._changes(current, basis)
            if changes is None:
                action: Literal["updated", "reassess", "unchanged"] = "unchanged"
            elif current.status == "completed":
                action = "reassess"
            else:
                action = "updated"
            operations.append(TaskOperation(
                action,
                vulnerability.id,
                vulnerability.cve_id,
                context,
                vulnerability.source_modified_at,
                current=current,
                reason=(
                    "产品 OTS 关联已停用"
                    if target_status == "disabled"
                    else "产品 OTS 关联已恢复"
                ),
                basis=basis,
                changes=changes,
            ))
        return TaskPlan(tuple(operations), self._result(operations, status=status))

    def plan(
        self,
        session: Session,
        *,
        vulnerabilities: list[Vulnerability],
        targets: list[CalculatedCandidate],
        existing_candidates: list[VulnerabilityOtsMatch],
        status: str,
        lock: bool = False,
    ) -> TaskPlan:
        vulnerability_by_id = {item.id: item for item in vulnerabilities}
        cve_by_id = {item.id: item.cve_id for item in vulnerabilities}
        target_by_key = {
            (item.vulnerability_id, item.ots_component_id): item for item in targets
        }
        existing_by_key = {
            (item.vulnerability_id, item.ots_component_id): item
            for item in existing_candidates
        }
        ots_ids = {key[1] for key in target_by_key} | {key[1] for key in existing_by_key}
        contexts_by_ots: dict[int, list[ProductOtsContext]] = {}
        for context in self._repository.list_product_contexts(session, ots_ids):
            contexts_by_ots.setdefault(context.ots_component_id, []).append(context)
        current_items = self._repository.list_current_assessments(
            session, set(vulnerability_by_id), lock=lock
        )
        current_by_key: dict[tuple[int, int], ProductAssessment] = {}
        for current in current_items:
            key = (current.product_ots_id, current.vulnerability_id)
            if key in current_by_key:
                raise RuntimeError("multiple current assessment revisions")
            current_by_key[key] = current

        operations: list[TaskOperation] = []
        for key, target in sorted(target_by_key.items()):
            contexts = contexts_by_ots.get(target.ots_component_id, [])
            if not contexts:
                operations.append(TaskOperation(
                    "skipped", target.vulnerability_id, target.cve_id, None,
                    target.source_modified_at, reason=NO_ACTIVE_PRODUCT_OTS,
                ))
                continue
            for context in contexts:
                reason = self._context_skip_reason(context)
                if reason:
                    operations.append(TaskOperation(
                        "skipped", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, reason=reason,
                    ))
                    continue
                current = current_by_key.get((context.product_ots_id, target.vulnerability_id))
                basis = self._basis(
                    vulnerability_by_id[target.vulnerability_id], target, context
                )
                changes = self._changes(current, basis)
                if current is None:
                    operations.append(TaskOperation(
                        "inserted", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, basis=basis,
                    ))
                elif current.assessment_basis_json is None or current.assessment_basis_sha256 is None:
                    operations.append(TaskOperation(
                        "updated", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current, basis=basis,
                    ))
                elif current.status == "completed" and changes is not None:
                    operations.append(TaskOperation(
                        "reassess", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current,
                        reason="自动复评依据已变化", basis=basis, changes=changes,
                    ))
                elif current.status == "pending" and self._empty_pending(current):
                    if changes is not None or current.owner_id != context.owner_id or current.based_on_source_modified_at != target.source_modified_at:
                        operations.append(TaskOperation(
                            "updated", target.vulnerability_id, target.cve_id, context,
                            target.source_modified_at, current=current,
                            basis=basis, changes=changes,
                        ))
                    else:
                        operations.append(TaskOperation(
                            "unchanged", target.vulnerability_id, target.cve_id, context,
                            target.source_modified_at, current=current, basis=basis,
                        ))
                elif changes is not None and current.status in {"pending", "submitted", "returned", "reassess"}:
                    operations.append(TaskOperation(
                        "updated", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current,
                        basis=basis, changes=changes,
                    ))
                else:
                    operations.append(TaskOperation(
                        "unchanged", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current, basis=basis,
                    ))

        removed_keys = sorted(set(existing_by_key) - set(target_by_key))
        for vulnerability_id, ots_component_id in removed_keys:
            vulnerability = vulnerability_by_id.get(vulnerability_id)
            if vulnerability is None:
                continue
            for context in contexts_by_ots.get(ots_component_id, []):
                current = current_by_key.get((context.product_ots_id, vulnerability_id))
                if current is None:
                    continue
                basis = self._basis(vulnerability, None, context)
                changes = self._changes(current, basis)
                if changes is None:
                    continue
                if current.status == "completed":
                    operations.append(TaskOperation(
                        "reassess", vulnerability_id, cve_by_id[vulnerability_id], context,
                        vulnerability.source_modified_at, current=current,
                        reason="OTS/CVE 候选已移除", basis=basis, changes=changes,
                    ))
                else:
                    operations.append(TaskOperation(
                        "updated", vulnerability_id, cve_by_id[vulnerability_id], context,
                        vulnerability.source_modified_at, current=current,
                        basis=basis, changes=changes,
                    ))

        operations.sort(key=lambda item: (
            item.cve_id,
            item.context.product_id if item.context else 0,
            item.context.product_version_id if item.context else 0,
            item.context.product_ots_id if item.context else 0,
            item.action,
        ))
        result = self._result(operations, status=status)
        return TaskPlan(tuple(operations), result)

    def apply(self, session: Session, plan: TaskPlan) -> dict[str, object]:
        if any(
            operation.action in {"inserted", "updated", "reassess"}
            for operation in plan.operations
        ) and not self._repository.current_bases_ready(session):
            raise RuntimeError("assessment basis initialization is required")
        change_types: set[str] = set()
        basis_fingerprints: list[dict[str, object]] = []
        revision_links: list[dict[str, object]] = []
        changed_count = 0
        for operation in plan.operations:
            if operation.action in {"inserted", "updated", "reassess"}:
                changed_count += 1
                if operation.basis is not None and len(basis_fingerprints) < 100:
                    basis_fingerprints.append({
                        "product_ots_id": (
                            operation.context.product_ots_id
                            if operation.context is not None else None
                        ),
                        "vulnerability_id": operation.vulnerability_id,
                        "basis_sha256": operation.basis.sha256,
                    })
                if isinstance(operation.changes, dict):
                    change_types.update(
                        str(item)
                        for item in operation.changes.get("change_types", [])
                    )
            if operation.action == "inserted":
                session.add(self._new_assessment(operation))
            elif operation.action == "updated":
                current = operation.current
                context = operation.context
                if current is None or context is None or operation.source_modified_at is None:
                    raise RuntimeError("invalid assessment update plan")
                values: dict[str, object] = {
                    "based_on_source_modified_at": operation.source_modified_at,
                    "reassess_changes_json": merge_reassessment_changes(
                        current.reassess_changes_json, operation.changes
                    ),
                }
                if current.status == "pending" and self._empty_pending(current):
                    values["owner_id"] = context.owner_id
                if operation.basis is not None:
                    values["assessment_basis_sha256"] = operation.basis.sha256
                    values["assessment_basis_json"] = operation.basis.data
                if not self._repository.update_current_if_version(
                    session,
                    assessment_id=current.id,
                    expected_status=current.status,
                    row_version=current.row_version,
                    values=values,
                ):
                    raise RuntimeError("assessment task update conflict")
            elif operation.action == "reassess":
                current = operation.current
                context = operation.context
                if current is None or context is None:
                    raise RuntimeError("invalid reassessment plan")
                child = clone_assessment_revision(
                    session,
                    self._revision_repository,
                    assessment=current,
                    expected_status="completed",
                    row_version=current.row_version,
                    parent_values={"is_current": False},
                    child_status="reassess",
                    owner_id=context.owner_id,
                    reassess_reason=operation.reason,
                    reassess_changes_json=operation.changes,
                    now=datetime.now(timezone.utc),
                    basis=operation.basis,
                )
                if child is None:
                    raise RuntimeError("assessment reassessment conflict")
                if len(revision_links) < 100:
                    revision_links.append({
                        "parent_assessment_id": current.id,
                        "parent_revision_no": current.revision_no,
                        "child_assessment_id": child.id,
                        "child_revision_no": child.revision_no,
                    })
        return {
            "change_types": sorted(change_types),
            "basis_fingerprints": basis_fingerprints,
            "revision_links": revision_links,
            "truncated_operation_count": max(0, changed_count - 100),
        }

    @staticmethod
    def _context_skip_reason(context: ProductOtsContext) -> str | None:
        if context.product_status != "active":
            return PRODUCT_DISABLED
        if context.product_version_status != "active":
            return PRODUCT_VERSION_DISABLED
        if not context.owner_available:
            return OWNER_UNAVAILABLE
        return None

    @staticmethod
    def _basis(
        vulnerability: Vulnerability,
        candidate: CalculatedCandidate | None,
        context: ProductOtsContext,
    ) -> AssessmentBasis:
        candidate_data = None if candidate is None else {
            "match_method": candidate.match_method,
            "match_evidence_json": candidate.evidence,
        }
        return build_assessment_basis(
            source=vulnerability,
            candidate=candidate_data,
            product_ots_id=context.product_ots_id,
            product_ots_status="active",
            kev_available=False,
        )

    @staticmethod
    def _changes(
        current: ProductAssessment | None, basis: AssessmentBasis
    ) -> dict[str, object] | None:
        if current is None or current.assessment_basis_json is None:
            return None
        if current.assessment_basis_sha256 == basis.sha256:
            return None
        return diff_assessment_basis(
            current.assessment_basis_json,
            basis.data,
            now=datetime.now(timezone.utc),
        )

    @staticmethod
    def _empty_pending(current: ProductAssessment) -> bool:
        fields = (
            current.analysis_summary,
            current.trigger_conditions,
            current.affected_functions,
            current.applicability_basis,
            current.product_impact,
            current.existing_controls,
            current.treatment,
            current.treatment_detail,
            current.evidence_text,
            current.environmental_score,
            current.environmental_vector,
            current.cvss_metrics_json,
            current.submitted_by,
            current.review_decision,
            current.reviewer_id,
        )
        return current.applicability == "pending" and all(value is None for value in fields)

    @staticmethod
    def _new_assessment(operation: TaskOperation) -> ProductAssessment:
        context = operation.context
        if context is None or operation.source_modified_at is None:
            raise RuntimeError("task source modified time is required")
        return ProductAssessment(
            product_ots_id=context.product_ots_id,
            vulnerability_id=operation.vulnerability_id,
            revision_no=1,
            parent_revision_id=None,
            is_current=True,
            status="pending",
            owner_id=context.owner_id,
            applicability="pending",
            based_on_source_modified_at=operation.source_modified_at,
            assessment_basis_sha256=operation.basis.sha256 if operation.basis else None,
            assessment_basis_json=operation.basis.data if operation.basis else None,
            row_version=1,
        )

    @staticmethod
    def _result(operations: list[TaskOperation], *, status: str) -> dict[str, object]:
        counts = {
            action: sum(item.action == action for item in operations)
            for action in ("inserted", "reassess", "updated", "unchanged", "skipped")
        }
        skip_reasons: dict[str, int] = {}
        for item in operations:
            if item.action == "skipped" and item.reason:
                skip_reasons[item.reason] = skip_reasons.get(item.reason, 0) + 1
        return {
            "schema_version": "1.0",
            "status": status,
            "task_inserted_count": counts["inserted"],
            "task_reassess_count": counts["reassess"],
            "task_updated_count": counts["updated"],
            "task_unchanged_count": counts["unchanged"],
            "task_skipped_count": counts["skipped"],
            "task_failed_count": 0,
            "skip_reason_counts": skip_reasons,
            "task_samples": [item.sample() for item in operations[:100]],
            "truncated_task_count": max(0, len(operations) - 100),
            "error_code": None,
        }

    @staticmethod
    def failed_result() -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "status": "failed",
            "task_inserted_count": 0,
            "task_reassess_count": 0,
            "task_updated_count": 0,
            "task_unchanged_count": 0,
            "task_skipped_count": 0,
            "task_failed_count": 1,
            "skip_reason_counts": {},
            "task_samples": [],
            "truncated_task_count": 0,
            "error_code": "MATCH_EXECUTION_FAILED",
        }
