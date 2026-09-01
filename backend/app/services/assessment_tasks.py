from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import TYPE_CHECKING, Literal

from sqlalchemy.orm import Session

from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability, VulnerabilityOtsMatch
from app.repositories.assessment_tasks import AssessmentTaskRepository, ProductOtsContext

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
            old_candidate = existing_by_key.get(key)
            material_change = old_candidate is not None and self._evidence_changed(old_candidate, target)
            for context in contexts:
                reason = self._context_skip_reason(context)
                if reason:
                    operations.append(TaskOperation(
                        "skipped", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, reason=reason,
                    ))
                    continue
                current = current_by_key.get((context.product_ots_id, target.vulnerability_id))
                if current is None:
                    operations.append(TaskOperation(
                        "inserted", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at,
                    ))
                elif current.status == "completed" and material_change:
                    operations.append(TaskOperation(
                        "reassess", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current,
                        reason="候选受影响范围或匹配依据已变化",
                    ))
                elif current.status == "pending" and self._empty_pending(current):
                    if current.owner_id != context.owner_id or current.based_on_source_modified_at != target.source_modified_at:
                        operations.append(TaskOperation(
                            "updated", target.vulnerability_id, target.cve_id, context,
                            target.source_modified_at, current=current,
                        ))
                    else:
                        operations.append(TaskOperation(
                            "unchanged", target.vulnerability_id, target.cve_id, context,
                            target.source_modified_at, current=current,
                        ))
                elif material_change and current.status in {"pending", "submitted", "returned", "reassess"}:
                    operations.append(TaskOperation(
                        "skipped", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current,
                        reason=ASSESSMENT_IN_PROGRESS,
                    ))
                else:
                    operations.append(TaskOperation(
                        "unchanged", target.vulnerability_id, target.cve_id, context,
                        target.source_modified_at, current=current,
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
                if current.status == "completed":
                    operations.append(TaskOperation(
                        "reassess", vulnerability_id, cve_by_id[vulnerability_id], context,
                        vulnerability.source_modified_at, current=current,
                        reason="OTS/CVE 候选已移除",
                    ))
                else:
                    operations.append(TaskOperation(
                        "skipped", vulnerability_id, cve_by_id[vulnerability_id], context,
                        vulnerability.source_modified_at, current=current,
                        reason=ASSESSMENT_IN_PROGRESS,
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

    def apply(self, session: Session, plan: TaskPlan) -> None:
        for operation in plan.operations:
            if operation.action == "inserted":
                session.add(self._new_assessment(operation))
            elif operation.action == "updated":
                current = operation.current
                context = operation.context
                if current is None or context is None or operation.source_modified_at is None:
                    raise RuntimeError("invalid assessment update plan")
                current.owner_id = context.owner_id
                current.based_on_source_modified_at = operation.source_modified_at
                current.row_version += 1
            elif operation.action == "reassess":
                current = operation.current
                if current is None:
                    raise RuntimeError("invalid reassessment plan")
                current.is_current = False
                session.add(self._reassessment(operation, current))

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
    def _evidence_changed(
        current: VulnerabilityOtsMatch, target: CalculatedCandidate
    ) -> bool:
        if current.match_content_sha256 == target.content_sha256:
            return False
        if current.match_method != target.match_method:
            return True
        current_evidence = json.dumps(
            current.match_evidence_json or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        target_evidence = json.dumps(
            target.evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return current_evidence != target_evidence

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
            row_version=1,
        )

    @staticmethod
    def _reassessment(
        operation: TaskOperation, current: ProductAssessment
    ) -> ProductAssessment:
        context = operation.context
        if context is None or operation.source_modified_at is None:
            raise RuntimeError("reassessment source modified time is required")
        return ProductAssessment(
            product_ots_id=current.product_ots_id,
            vulnerability_id=current.vulnerability_id,
            revision_no=current.revision_no + 1,
            parent_revision_id=current.id,
            is_current=True,
            status="reassess",
            owner_id=context.owner_id,
            analysis_summary=current.analysis_summary,
            trigger_conditions=current.trigger_conditions,
            affected_functions=current.affected_functions,
            applicability=current.applicability,
            applicability_basis=current.applicability_basis,
            product_impact=current.product_impact,
            existing_controls=current.existing_controls,
            treatment=current.treatment,
            treatment_detail=current.treatment_detail,
            evidence_text=current.evidence_text,
            cvss_version=current.cvss_version,
            environmental_score=current.environmental_score,
            environmental_vector=current.environmental_vector,
            cvss_metrics_json=current.cvss_metrics_json,
            calculator_version=current.calculator_version,
            based_on_source_modified_at=operation.source_modified_at,
            reassess_reason=operation.reason,
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
