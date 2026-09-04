from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url

from app.main import create_app
from app.infrastructure.settings import Settings
from app.migrations import apply_migrations
from app.models.assessments import ProductAssessment
from app.models.imports import Vulnerability
from app.models.scopes import UserProductScope
from app.models.user import AuditLog, Base
from app.repositories.assessment_editor import AssessmentEditorRepository
from app.schemas.assessment_editor import (
    AssessmentActionRequest,
    AssessmentDraftUpdateRequest,
    AssessmentRevisionCreateRequest,
    AssessmentReturnRequest,
)
from app.services.assessment_editor import (
    AssessmentActionConflictError,
    AssessmentNotEditableError,
    AssessmentVersionConflictError,
    REVISION_COPY_FIELDS,
    REVISION_EVENT_FIELDS,
    REVISION_SYSTEM_FIELDS,
)
from app.services.authentication import AuthenticationService, PublicUser
from tests.test_vulnerability_workbench import grant_version_scope, login, seed_catalog


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{tmp_path / 'assessment-editor.db'}")
    monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(tmp_path / "incoming"))
    monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(tmp_path / "archive"))
    application = create_app()
    Base.metadata.create_all(application.state.database.engine)
    AuthenticationService(application.state.database.session_factory).initialize_admin(
        "admin", "初始管理员", "admin-password"
    )
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client
    application.state.database.engine.dispose()


def assessment_id(
    client: TestClient, status: str, *, current: bool = True, last: bool = False
) -> int:
    with client.app.state.database.session_factory() as session:
        return int(
            session.scalar(
                select(ProductAssessment.id)
                .where(
                    ProductAssessment.status == status,
                    ProductAssessment.is_current.is_(current),
                )
                .order_by(ProductAssessment.id.desc() if last else ProductAssessment.id)
                .limit(1)
            )
        )


def draft_payload(row_version: int = 1, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "row_version": row_version,
        "analysis_summary": None,
        "trigger_conditions": None,
        "affected_functions": None,
        "applicability": "pending",
        "applicability_basis": None,
        "product_impact": None,
        "existing_controls": None,
        "treatment": None,
        "treatment_detail": None,
        "evidence_text": None,
        "cvss_metrics": None,
    }
    payload.update(overrides)
    return payload


def enable_source_cvss31(client: TestClient, target_id: int) -> None:
    with client.app.state.database.session_factory.begin() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        vulnerability = session.get(Vulnerability, assessment.vulnerability_id)
        assert vulnerability is not None
        vulnerability.cvss31_score = 9.8
        vulnerability.cvss31_severity = "CRITICAL"
        vulnerability.cvss31_vector = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
        vulnerability.cvss31_source = "nvd@nist.gov"


def complete_assessment(client: TestClient, target_id: int) -> None:
    with client.app.state.database.session_factory.begin() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        assessment.analysis_summary = "完整分析摘要"
        assessment.trigger_conditions = "存在可达攻击路径"
        assessment.affected_functions = "网络服务接口"
        assessment.applicability = "affected"
        assessment.applicability_basis = "产品使用受影响版本"
        assessment.product_impact = "可能导致远程代码执行"
        assessment.existing_controls = "当前仅有网络隔离"
        assessment.treatment = "patch_or_upgrade"
        assessment.treatment_detail = "升级到修复版本"
        assessment.evidence_text = "内部验证记录 SEC-001"


def submit_assessment(client: TestClient, target_id: int, row_version: int = 1):
    client.cookies.clear()
    login(client, "owner", "user-password")
    return client.post(
        f"/api/v1/assessments/{target_id}/submit",
        json={"row_version": row_version},
    )


def test_submit_requires_complete_persisted_snapshot_and_freezes_revision(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")

    incomplete = submit_assessment(client, target_id)
    assert incomplete.status_code == 422
    assert incomplete.json()["code"] == "ASSESSMENT_SUBMIT_INCOMPLETE"
    assert {item["path"] for item in incomplete.json()["fields"]} == {
        "analysis_summary", "trigger_conditions", "affected_functions", "applicability",
        "applicability_basis", "product_impact", "existing_controls", "treatment",
        "treatment_detail", "evidence_text",
    }

    complete_assessment(client, target_id)
    submitted = submit_assessment(client, target_id)
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["status"] == "submitted"
    assert body["row_version"] == 2
    assert body["editable"] is False
    assert body["submitted_by"] == 2
    assert body["submitted_at"] is not None
    assert body["actions"] == {
        "can_submit": False, "can_approve": False, "can_return": False,
        "can_create_revision": False,
        "unavailable_reason": "ASSESSMENT_ALREADY_SUBMITTED",
    }
    with client.app.state.database.session_factory() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        assert assessment.status == "submitted"
        assert assessment.submitted_by == 2
        audits = session.scalars(
            select(AuditLog).where(AuditLog.object_id == str(target_id))
        ).all()
        assert len(audits) == 1
        assert audits[0].detail_json["action"] == "submit"
        assert "完整分析摘要" not in str(audits[0].detail_json)


def test_submit_rejects_self_review_assignment_stale_and_non_pending(
    client: TestClient,
) -> None:
    scope = seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    with client.app.state.database.session_factory.begin() as session:
        from app.models.products import ProductVersion
        version = session.get(ProductVersion, int(scope["version_a"]["id"]))
        assert version is not None
        version.reviewer_id = int(scope["owner"]["id"])

    self_review = submit_assessment(client, target_id)
    assert self_review.status_code == 409
    assert self_review.json()["code"] == "REVIEWER_REASSIGNMENT_REQUIRED"

    with client.app.state.database.session_factory.begin() as session:
        from app.models.products import ProductVersion
        version = session.get(ProductVersion, int(scope["version_a"]["id"]))
        assert version is not None
        version.reviewer_id = int(scope["reviewer"]["id"])
    assert submit_assessment(client, target_id, row_version=99).status_code == 409
    submitted = submit_assessment(client, target_id)
    assert submitted.status_code == 200
    repeated = submit_assessment(client, target_id, row_version=2)
    assert repeated.status_code == 409
    assert repeated.json()["code"] == "ASSESSMENT_ACTION_CONFLICT"


def test_submit_rejects_inconsistent_saved_environmental_result(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    enable_source_cvss31(client, target_id)
    with client.app.state.database.session_factory.begin() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        assessment.cvss_version = "3.1"
        assessment.cvss_metrics_json = {"CR": "H"}
        assessment.environmental_score = 0.1
        assessment.environmental_vector = "forged"
        assessment.calculator_version = "ots-cvss31-1"

    response = submit_assessment(client, target_id)
    assert response.status_code == 409
    assert response.json()["code"] == "ASSESSMENT_ACTION_CONFLICT"
    with client.app.state.database.session_factory() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        assert assessment.status == "pending"
        assert assessment.submitted_by is None


def test_current_reviewer_can_approve_but_cannot_self_review_or_repeat(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    assert submit_assessment(client, target_id).status_code == 200

    client.cookies.clear()
    login(client, "reviewer", "user-password")
    detail = client.get(f"/api/v1/assessments/{target_id}")
    assert detail.json()["actions"]["can_approve"] is True
    approved = client.post(
        f"/api/v1/assessments/{target_id}/approve", json={"row_version": 2}
    )
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "completed"
    assert body["review_decision"] == "approved"
    assert body["reviewer_id"] == 3
    assert body["reviewed_at"] is not None
    assert body["row_version"] == 3
    repeated = client.post(
        f"/api/v1/assessments/{target_id}/approve", json={"row_version": 3}
    )
    assert repeated.status_code == 409
    with client.app.state.database.session_factory() as session:
        assert session.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.object_id == str(target_id))
        ) == 2


def test_return_requires_comment_rejects_extra_fields_and_preserves_conclusion(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    assert submit_assessment(client, target_id).status_code == 200
    client.cookies.clear()
    login(client, "reviewer", "user-password")

    blank = client.post(
        f"/api/v1/assessments/{target_id}/return",
        json={"row_version": 2, "review_comment": "   "},
    )
    extra = client.post(
        f"/api/v1/assessments/{target_id}/return",
        json={"row_version": 2, "review_comment": "补充依据", "applicability": "not_affected"},
    )
    assert blank.status_code == 422
    assert blank.json()["fields"][0]["path"] == "review_comment"
    assert extra.status_code == 422

    returned = client.post(
        f"/api/v1/assessments/{target_id}/return",
        json={"row_version": 2, "review_comment": "  请补充影响依据  "},
    )
    assert returned.status_code == 200
    body = returned.json()
    current = body["current_revision"]
    reviewed = body["reviewed_revision"]
    assert current["assessment_id"] != target_id
    assert current["revision_no"] == reviewed["revision_no"] + 1
    assert current["parent_revision_id"] == target_id
    assert current["status"] == "returned"
    assert current["is_current"] is True
    assert current["review_decision"] is None
    assert current["review_comment"] is None
    assert current["submitted_by"] is None
    assert current["submitted_at"] is None
    assert current["reviewer_id"] is None
    assert current["reviewed_at"] is None
    assert current["return_reason"] == "请补充影响依据"
    assert current["reason_type"] == "review_return"
    assert current["editable"] is False
    assert current["draft"]["analysis_summary"] == "完整分析摘要"
    assert reviewed == {
        "assessment_id": target_id,
        "revision_no": 1,
        "status": "returned",
        "review_decision": "returned",
        "review_comment": "请补充影响依据",
        "reviewer_id": 3,
        "reviewed_at": reviewed["reviewed_at"],
    }
    client.cookies.clear()
    login(client, "owner", "user-password")
    parent_refused = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(row_version=3, analysis_summary="覆盖提交结论"),
    )
    edited = client.put(
        f"/api/v1/assessments/{current['assessment_id']}/draft",
        json=draft_payload(row_version=1, analysis_summary="修订后的分析"),
    )
    assert parent_refused.status_code == 409
    assert edited.status_code == 200
    assert edited.json()["draft"]["analysis_summary"] == "修订后的分析"

    with client.app.state.database.session_factory() as session:
        parent = session.get(ProductAssessment, target_id)
        child = session.get(ProductAssessment, current["assessment_id"])
        assert parent is not None and child is not None
        assert parent.is_current is False
        assert parent.submitted_by == 2
        assert parent.review_decision == "returned"
        assert parent.review_comment == "请补充影响依据"
        assert child.is_current is True
        assert session.scalar(
            select(func.count(ProductAssessment.id)).where(
                ProductAssessment.product_ots_id == parent.product_ots_id,
                ProductAssessment.vulnerability_id == parent.vulnerability_id,
                ProductAssessment.is_current.is_(True),
            )
        ) == 1


def test_completed_owner_creates_revision_and_resubmits_without_overwriting_parent(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    assert submit_assessment(client, target_id).status_code == 200
    client.cookies.clear()
    login(client, "reviewer", "user-password")
    approved = client.post(
        f"/api/v1/assessments/{target_id}/approve", json={"row_version": 2}
    )
    assert approved.status_code == 200

    client.cookies.clear()
    login(client, "owner", "user-password")
    blank = client.post(
        f"/api/v1/assessments/{target_id}/revisions",
        json={"row_version": 3, "revision_reason": "   "},
    )
    extra = client.post(
        f"/api/v1/assessments/{target_id}/revisions",
        json={"row_version": 3, "revision_reason": "重新验证", "revision_no": 99},
    )
    assert blank.status_code == 422
    assert blank.json()["fields"][0]["path"] == "revision_reason"
    assert extra.status_code == 422

    created = client.post(
        f"/api/v1/assessments/{target_id}/revisions",
        json={"row_version": 3, "revision_reason": "  产品配置发生调整  "},
    )
    assert created.status_code == 200
    child = created.json()
    assert child["parent_revision_id"] == target_id
    assert child["revision_no"] == 2
    assert child["status"] == "reassess"
    assert child["reason_type"] == "manual_revision"
    assert child["reassess_reason"] == "产品配置发生调整"
    assert child["editable"] is True
    assert child["actions"]["can_submit"] is True

    saved = client.put(
        f"/api/v1/assessments/{child['assessment_id']}/draft",
        json=draft_payload(
            row_version=1,
            analysis_summary="修订分析",
            trigger_conditions="存在可达攻击路径",
            affected_functions="网络服务接口",
            applicability="affected",
            applicability_basis="产品使用受影响版本",
            product_impact="可能导致远程代码执行",
            existing_controls="当前仅有网络隔离",
            treatment="patch_or_upgrade",
            treatment_detail="升级到修复版本",
            evidence_text="内部验证记录 SEC-002",
        ),
    )
    assert saved.status_code == 200
    resubmitted = client.post(
        f"/api/v1/assessments/{child['assessment_id']}/submit",
        json={"row_version": 2},
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["status"] == "submitted"

    with client.app.state.database.session_factory() as session:
        parent = session.get(ProductAssessment, target_id)
        assert parent is not None
        assert parent.status == "completed"
        assert parent.review_decision == "approved"
        assert parent.submitted_by == 2
        assert parent.reviewer_id == 3


def test_revision_history_detail_and_comparison_are_scoped_and_read_only(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    assert submit_assessment(client, target_id).status_code == 200
    client.cookies.clear()
    login(client, "reviewer", "user-password")
    returned = client.post(
        f"/api/v1/assessments/{target_id}/return",
        json={"row_version": 2, "review_comment": "<b>补充依据</b>"},
    )
    assert returned.status_code == 200
    current_id = returned.json()["current_revision"]["assessment_id"]

    client.cookies.clear()
    login(client, "owner", "user-password")
    with client.app.state.database.session_factory() as session:
        audit_count_before_reads = session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.object_type == "product_assessment"
            )
        )
    history = client.get(f"/api/v1/assessments/{current_id}/revisions")
    assert history.status_code == 200
    assert [item["revision_no"] for item in history.json()["items"]] == [2, 1]
    assert history.json()["items"][0]["is_current"] is True
    assert history.json()["items"][1]["review_comment"] == "<b>补充依据</b>"

    historical = client.get(f"/api/v1/assessments/{target_id}")
    assert historical.status_code == 200
    assert historical.json()["editable"] is False
    assert historical.json()["current_revision_id"] == current_id
    assert not any(historical.json()["actions"].values())
    historical_save = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(row_version=historical.json()["row_version"]),
    )
    assert historical_save.status_code == 409
    assert historical_save.json()["code"] == "ASSESSMENT_NOT_EDITABLE"
    assert historical_save.json()["current_revision_id"] == current_id

    comparison = client.get(
        f"/api/v1/assessments/{current_id}/revision-comparison"
        f"?base_revision_id={target_id}&target_revision_id={current_id}"
    )
    assert comparison.status_code == 200
    assert comparison.json()["base_revision_id"] == target_id
    assert comparison.json()["target_revision_id"] == current_id
    assert {change["field"] for change in comparison.json()["changes"]} >= {
        "submitted_by", "review_decision"
    }

    out_of_scope = assessment_id(client, "submitted", last=True)
    forbidden = client.get(f"/api/v1/assessments/{out_of_scope}/revisions")
    assert forbidden.status_code == 403
    cross_chain = client.get(
        f"/api/v1/assessments/{current_id}/revision-comparison"
        f"?base_revision_id={target_id}&target_revision_id={out_of_scope}"
    )
    assert cross_chain.status_code in {403, 422}
    with client.app.state.database.session_factory() as session:
        audit_count_after_reads = session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.object_type == "product_assessment"
            )
        )
    assert audit_count_after_reads == audit_count_before_reads


def test_return_revision_and_audit_roll_back_together(
    client: TestClient, monkeypatch,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    assert submit_assessment(client, target_id).status_code == 200
    service = client.app.state.assessment_editor_service
    original = service._create_child_revision

    def fail_after_revision_writes(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("forced revision rollback")

    monkeypatch.setattr(service, "_create_child_revision", fail_after_revision_writes)
    client.cookies.clear()
    login(client, "reviewer", "user-password")
    failed = client.post(
        f"/api/v1/assessments/{target_id}/return",
        json={"row_version": 2, "review_comment": "不得进入审计的完整退回意见"},
    )
    assert failed.status_code == 500

    with client.app.state.database.session_factory() as session:
        parent = session.get(ProductAssessment, target_id)
        assert parent is not None
        assert parent.status == "submitted"
        assert parent.is_current is True
        assert parent.review_decision is None
        assert session.scalar(
            select(func.count(ProductAssessment.id)).where(
                ProductAssessment.product_ots_id == parent.product_ots_id,
                ProductAssessment.vulnerability_id == parent.vulnerability_id,
            )
        ) == 1
        audits = session.scalars(
            select(AuditLog).where(AuditLog.object_id == str(target_id))
        ).all()
        assert [item.detail_json["action"] for item in audits] == ["submit"]


def test_revision_clone_field_policy_covers_complete_model() -> None:
    assert set(ProductAssessment.__table__.columns.keys()) == (
        set(REVISION_COPY_FIELDS)
        | set(REVISION_EVENT_FIELDS)
        | set(REVISION_SYSTEM_FIELDS)
    )


def test_review_uses_current_assignment_scope_role_and_blocks_submitter(
    client: TestClient,
) -> None:
    scope = seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    assert submit_assessment(client, target_id).status_code == 200

    with client.app.state.database.session_factory.begin() as session:
        from app.models.products import ProductVersion
        version = session.get(ProductVersion, int(scope["version_a"]["id"]))
        assessment = session.get(ProductAssessment, target_id)
        assert version is not None and assessment is not None
        version.reviewer_id = int(scope["replacement"]["id"])
        assessment.submitted_by = int(scope["replacement"]["id"])

    client.cookies.clear()
    login(client, "reviewer", "user-password")
    old_reviewer = client.post(
        f"/api/v1/assessments/{target_id}/approve", json={"row_version": 2}
    )
    assert old_reviewer.status_code == 403

    client.cookies.clear()
    login(client)
    grant_version_scope(
        client, int(scope["replacement"]["id"]), int(scope["product_a"]["id"]),
        int(scope["version_a"]["id"]),
    )
    client.cookies.clear()
    login(client, "replacement", "user-password")
    self_review = client.post(
        f"/api/v1/assessments/{target_id}/approve", json={"row_version": 2}
    )
    assert self_review.status_code == 403
    assert self_review.json()["code"] == "ASSESSMENT_SELF_REVIEW_FORBIDDEN"


def test_action_and_audit_roll_back_together_on_failure(
    client: TestClient, monkeypatch,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    complete_assessment(client, target_id)
    service = client.app.state.assessment_editor_service
    original = service._transition

    def fail_after_writes(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("forced rollback")

    monkeypatch.setattr(service, "_transition", fail_after_writes)
    response = submit_assessment(client, target_id)
    assert response.status_code == 500
    with client.app.state.database.session_factory() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        assert assessment.status == "pending"
        assert assessment.submitted_by is None
        assert assessment.row_version == 1
        assert session.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.object_id == str(target_id))
        ) == 0


def test_assessment_actions_openapi_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    for action in ("submit", "approve", "return"):
        operation = schema["paths"][f"/api/v1/assessments/{{assessment_id}}/{action}"]["post"]
        assert set(operation["responses"]) >= {"200", "403", "404", "409", "422"}
    detail_schema = schema["components"]["schemas"]["AssessmentDetailResponse"]["properties"]
    assert {
        "actions", "submitted_by", "submitted_at", "review_decision", "review_comment",
        "reviewer_id", "reviewed_at", "parent_revision_id", "current_revision_id",
        "reason_type", "reassessment",
    } <= set(detail_schema)
    action_schema = schema["components"]["schemas"]["AssessmentActionsResponse"]["properties"]
    assert "can_create_revision" in action_schema
    assert "/api/v1/assessments/{assessment_id}/revisions" in schema["paths"]
    assert "/api/v1/assessments/{assessment_id}/revision-comparison" in schema["paths"]
    return_operation = schema["paths"]["/api/v1/assessments/{assessment_id}/return"]["post"]
    return_schema = return_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert return_schema["$ref"].endswith("/AssessmentReturnResponse")


def test_owner_reads_current_and_historical_details_with_server_editability(
    client: TestClient,
) -> None:
    seed_catalog(client)
    current_id = assessment_id(client, "pending")
    historical_id = assessment_id(client, "pending", current=False)
    client.cookies.clear()
    login(client, "owner", "user-password")

    current = client.get(f"/api/v1/assessments/{current_id}")
    historical = client.get(f"/api/v1/assessments/{historical_id}")

    assert current.status_code == 200
    assert current.json() == {
        "assessment_id": current_id,
        "revision_no": 1,
        "parent_revision_id": None,
        "current_revision_id": current_id,
        "is_current": True,
        "status": "pending",
        "owner_id": 2,
        "row_version": 1,
        "editable": True,
        "submitted_by": None,
        "submitted_at": None,
        "review_decision": None,
        "review_comment": None,
        "reviewer_id": None,
        "reviewed_at": None,
        "actions": {
            "can_submit": True,
            "can_approve": False,
            "can_return": False,
            "can_create_revision": False,
            "unavailable_reason": None,
        },
        "return_reason": None,
        "reassess_reason": None,
        "reason_type": None,
        "reassessment": None,
        "product": {"id": 1, "name": "产品 P-A"},
        "product_version": {"id": 1, "version_no": "1.0"},
        "ots": {"id": 1, "name": "OpenSSL", "version": "1.0"},
        "vulnerability": {
            "id": 4,
            "cve_id": "CVE-2026-2001",
            "source_status": "Analyzed",
            "description": "队列漏洞 1",
            "cvss31_score": None,
            "cvss31_severity": None,
            "cvss31_vector": None,
            "cvss31_source": None,
            "is_kev": False,
        },
        "candidate": None,
        "candidate_disclaimer": "候选不等于产品受影响",
        "draft": {
            "analysis_summary": None,
            "trigger_conditions": None,
            "affected_functions": None,
            "applicability": "pending",
            "applicability_basis": None,
            "product_impact": None,
            "existing_controls": None,
            "treatment": None,
            "treatment_detail": None,
            "evidence_text": None,
            "cvss_metrics": None,
        },
        "environmental_scoring": {
            "available": False,
            "unavailable_reason": "SOURCE_NOT_PROVIDED",
            "metrics": None,
            "score": None,
            "vector": None,
            "calculator_version": None,
        },
    }
    assert historical.status_code == 200
    assert historical.json()["is_current"] is False
    assert historical.json()["editable"] is False


def test_returned_and_reassess_details_expose_reasons_as_read_only_text(
    client: TestClient,
) -> None:
    seed_catalog(client)
    returned_id = assessment_id(client, "returned")
    reassess_id = assessment_id(client, "reassess")
    with client.app.state.database.session_factory.begin() as session:
        session.get(ProductAssessment, returned_id).review_comment = "<b>补充影响依据</b>"
        session.get(ProductAssessment, reassess_id).reassess_reason = "来源范围变化"
    client.cookies.clear()
    login(client, "owner", "user-password")

    returned = client.get(f"/api/v1/assessments/{returned_id}")
    reassess = client.get(f"/api/v1/assessments/{reassess_id}")

    assert returned.json()["return_reason"] == "<b>补充影响依据</b>"
    assert reassess.json()["reassess_reason"] == "来源范围变化"


def test_admin_and_reviewer_can_read_but_cannot_edit(client: TestClient) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")

    for login_name, password in (("admin", "admin-password"), ("reviewer", "user-password")):
        client.cookies.clear()
        login(client, login_name, password)
        detail = client.get(f"/api/v1/assessments/{target_id}")
        update = client.put(
            f"/api/v1/assessments/{target_id}/draft",
            json=draft_payload(analysis_summary="不允许代写"),
        )
        assert detail.status_code == 200
        assert detail.json()["editable"] is False
        assert update.status_code == 403
        assert update.json()["code"] == "ASSESSMENT_FORBIDDEN"


def test_detail_distinguishes_forbidden_and_not_found_without_leaking_data(
    client: TestClient,
) -> None:
    scope = seed_catalog(client)
    out_of_scope_id = assessment_id(client, "submitted", last=True)
    client.cookies.clear()
    login(client, "owner", "user-password")

    forbidden = client.get(f"/api/v1/assessments/{out_of_scope_id}")
    missing = client.get("/api/v1/assessments/999999")

    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ASSESSMENT_FORBIDDEN"
    assert set(forbidden.json()) == {"code", "message", "correlation_id"}
    assert str(scope["product_b"]["product_name"]) not in forbidden.text
    assert missing.status_code == 404
    assert missing.json()["code"] == "ASSESSMENT_NOT_FOUND"


def test_owner_saves_partial_draft_with_normalization_and_audit_summary(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    client.cookies.clear()
    login(client, "owner", "user-password")

    response = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(
            analysis_summary="  仅保存分析摘要  ",
            trigger_conditions="   ",
            evidence_text="<script>alert('x')</script>",
        ),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["revision_no"] == 1
    assert body["row_version"] == 2
    assert body["draft"]["analysis_summary"] == "仅保存分析摘要"
    assert body["draft"]["trigger_conditions"] is None
    assert body["draft"]["evidence_text"] == "<script>alert('x')</script>"
    with client.app.state.database.session_factory() as session:
        audit = session.scalar(
            select(AuditLog)
            .where(
                AuditLog.object_type == "product_assessment",
                AuditLog.object_id == str(target_id),
            )
            .order_by(AuditLog.id.desc())
        )
        assert audit is not None
        assert audit.user_id == 2
        assert audit.detail_json["revision_no"] == 1
        assert audit.detail_json["row_version"] == {"from": 1, "to": 2}
        assert set(audit.detail_json["changed_fields"]) == {
            "analysis_summary",
            "evidence_text",
        }
        assert "alert" not in str(audit.detail_json)
        assert audit.detail_json["changes"]["evidence_text"]["to"]["length"] == 27


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"applicability": "not_affected"}, "applicability_basis"),
        ({"applicability": "affected"}, "applicability_basis"),
        ({"treatment": "accept_risk"}, "treatment_detail"),
        ({"treatment": "no_action"}, "treatment_detail"),
    ],
)
def test_conditional_validation_is_atomic(
    client: TestClient, overrides: dict[str, object], field: str
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    client.cookies.clear()
    login(client, "owner", "user-password")

    response = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(analysis_summary="不得部分保存", **overrides),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ASSESSMENT_VALIDATION_ERROR"
    assert response.json()["fields"] == [{"path": field, "message": "此字段为必填项"}]
    with client.app.state.database.session_factory() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment.analysis_summary is None
        assert session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.object_type == "product_assessment",
                AuditLog.object_id == str(target_id),
            )
        ) == 0


def test_invalid_enum_and_oversized_text_return_field_paths(client: TestClient) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    client.cookies.clear()
    login(client, "owner", "user-password")

    invalid = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(applicability="unknown"),
    )
    oversized = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(analysis_summary="x" * 10001),
    )

    assert invalid.status_code == 422
    assert invalid.json()["code"] == "ASSESSMENT_VALIDATION_ERROR"
    assert invalid.json()["fields"][0]["path"] == "applicability"
    assert oversized.status_code == 422
    assert oversized.json()["fields"][0]["path"] == "analysis_summary"


def test_stale_version_and_non_editable_state_do_not_overwrite(client: TestClient) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    submitted_id = assessment_id(client, "submitted")
    client.cookies.clear()
    login(client, "owner", "user-password")

    first = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(analysis_summary="客户端一"),
    )
    stale = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(analysis_summary="客户端二"),
    )
    not_editable = client.put(
        f"/api/v1/assessments/{submitted_id}/draft",
        json=draft_payload(analysis_summary="旧修订"),
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "ASSESSMENT_VERSION_CONFLICT"
    assert not_editable.status_code == 409
    assert not_editable.json()["code"] == "ASSESSMENT_NOT_EDITABLE"
    with client.app.state.database.session_factory() as session:
        assert session.get(ProductAssessment, target_id).analysis_summary == "客户端一"


def test_scope_revocation_and_no_change_save_do_not_write_audit(client: TestClient) -> None:
    scope = seed_catalog(client)
    target_id = assessment_id(client, "pending")
    client.cookies.clear()
    login(client, "owner", "user-password")

    unchanged = client.put(
        f"/api/v1/assessments/{target_id}/draft", json=draft_payload()
    )
    with client.app.state.database.session_factory() as session:
        audit_count = session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.object_type == "product_assessment",
                AuditLog.object_id == str(target_id),
            )
        )
    assert unchanged.status_code == 200
    assert unchanged.json()["row_version"] == 1
    assert audit_count == 0

    client.cookies.clear()
    login(client)
    revoke = client.delete(
        f"/api/v1/users/{scope['owner']['id']}/scopes/{scope['owner_scope']['id']}"
    )
    assert revoke.status_code == 204
    client.cookies.clear()
    login(client, "owner", "user-password")
    forbidden = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(analysis_summary="范围撤销后保存"),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ASSESSMENT_FORBIDDEN"


def test_assessment_editor_openapi_contract(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/api/v1/assessments/{assessment_id}"]["get"]["responses"]["200"]
    draft_operation = schema["paths"]["/api/v1/assessments/{assessment_id}/draft"]["put"]
    assert draft_operation["responses"]["200"]
    assert set(draft_operation["responses"]) >= {"200", "403", "404", "409", "422"}
    request_ref = draft_operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    request_name = request_ref.rsplit("/", 1)[-1]
    properties = schema["components"]["schemas"][request_name]["properties"]
    assert set(properties) == set(draft_payload())


def test_detail_and_save_environmental_score_from_current_source(client: TestClient) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    enable_source_cvss31(client, target_id)
    client.cookies.clear()
    login(client, "owner", "user-password")

    before = client.get(f"/api/v1/assessments/{target_id}")
    saved = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(cvss_metrics={"CR": "H", "MAV": "A"}),
    )

    assert before.status_code == 200
    assert before.json()["vulnerability"] | {
        "cvss31_vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        "cvss31_source": "nvd@nist.gov",
    } == before.json()["vulnerability"]
    assert before.json()["environmental_scoring"] == {
        "available": True,
        "unavailable_reason": None,
        "metrics": None,
        "score": None,
        "vector": None,
        "calculator_version": None,
    }
    assert saved.status_code == 200
    scoring = saved.json()["environmental_scoring"]
    assert scoring["available"] is True
    assert scoring["metrics"] == {
        "CR": "H", "IR": "X", "AR": "X", "MAV": "A", "MAC": "X",
        "MPR": "X", "MUI": "X", "MS": "X", "MC": "X", "MI": "X", "MA": "X",
    }
    assert scoring["score"] == 8.8
    assert scoring["vector"].startswith("CVSS:3.1/AV:N/AC:L")
    assert scoring["calculator_version"] == "ots-cvss31-1"
    assert saved.json()["row_version"] == 2

    with client.app.state.database.session_factory() as session:
        assessment = session.get(ProductAssessment, target_id)
        assert assessment is not None
        assert assessment.cvss_version == "3.1"
        assert float(assessment.environmental_score) == 8.8
        assert assessment.cvss_metrics_json == scoring["metrics"]
        audit = session.scalar(
            select(AuditLog).where(AuditLog.object_id == str(target_id)).order_by(AuditLog.id.desc())
        )
        assert audit is not None
        assert "cvss_metrics_json" in audit.detail_json["changed_fields"]


def test_repeating_same_environmental_metrics_is_an_audit_free_noop(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    enable_source_cvss31(client, target_id)
    client.cookies.clear()
    login(client, "owner", "user-password")

    first = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(cvss_metrics={"CR": "H"}),
    )
    second = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(row_version=2, cvss_metrics={"CR": "H"}),
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["row_version"] == second.json()["row_version"] == 2
    with client.app.state.database.session_factory() as session:
        assert session.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.object_id == str(target_id))
        ) == 1


def test_missing_or_invalid_source_refuses_environmental_save_without_audit(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    client.cookies.clear()
    login(client, "owner", "user-password")

    missing_detail = client.get(f"/api/v1/assessments/{target_id}")
    missing_save = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(cvss_metrics={"CR": "H"}),
    )
    with client.app.state.database.session_factory.begin() as session:
        assessment = session.get(ProductAssessment, target_id)
        vulnerability = session.get(Vulnerability, assessment.vulnerability_id)
        vulnerability.cvss31_vector = "CVSS:3.1/AV:N/AC:L"
    invalid_detail = client.get(f"/api/v1/assessments/{target_id}")

    assert missing_detail.json()["environmental_scoring"]["available"] is False
    assert missing_detail.json()["environmental_scoring"]["unavailable_reason"] == "SOURCE_NOT_PROVIDED"
    assert missing_save.status_code == 422
    assert missing_save.json()["code"] == "CVSS31_SOURCE_UNAVAILABLE"
    assert missing_save.json()["fields"][0]["path"] == "cvss_metrics"
    assert invalid_detail.json()["environmental_scoring"]["available"] is False
    assert invalid_detail.json()["environmental_scoring"]["unavailable_reason"] == "SOURCE_VECTOR_INVALID"


def test_environmental_payload_rejects_invalid_metrics_and_forged_derived_fields(
    client: TestClient,
) -> None:
    seed_catalog(client)
    target_id = assessment_id(client, "pending")
    enable_source_cvss31(client, target_id)
    client.cookies.clear()
    login(client, "owner", "user-password")

    invalid = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(cvss_metrics={"VC": "H"}),
    )
    forged = client.put(
        f"/api/v1/assessments/{target_id}/draft",
        json=draft_payload(
            cvss_metrics={"CR": "H"}, environmental_score=0.1,
            environmental_vector="forged", calculator_version="attacker",
        ),
    )

    assert invalid.status_code == 422
    assert invalid.json()["fields"][0]["path"] == "cvss_metrics.VC"
    assert forged.status_code == 422


def test_mysql_two_sessions_prevent_lost_update_and_keep_eleven_tables(
    monkeypatch, tmp_path: Path
) -> None:
    configured_url = Settings.from_environment().database_url
    assert configured_url is not None
    url = make_url(configured_url)
    database_name = f"ots12_test_{uuid4().hex}"
    admin_engine = create_engine(url.set(database="mysql"))
    test_engine = None
    application = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"))
        test_url = url.set(database=database_name)
        test_engine = create_engine(test_url)
        assert apply_migrations(test_engine, Path(__file__).parents[1] / "migrations") == list(
            range(1, 14)
        )
        assert len(
            [
                name
                for name in inspect(test_engine).get_table_names()
                if name != "schema_migration"
            ]
        ) == 11

        monkeypatch.setenv("OTS_DATABASE_URL", test_url.render_as_string(hide_password=False))
        monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(tmp_path / "incoming"))
        monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(tmp_path / "archive"))
        application = create_app()
        AuthenticationService(application.state.database.session_factory).initialize_admin(
            "admin", "初始管理员", "admin-password"
        )
        with TestClient(application, raise_server_exceptions=False) as mysql_client:
            seed_catalog(mysql_client)
            target_id = assessment_id(mysql_client, "pending")
            repository = AssessmentEditorRepository()
            first_session = application.state.database.session_factory()
            second_session = application.state.database.session_factory()
            try:
                first = first_session.get(ProductAssessment, target_id)
                second = second_session.get(ProductAssessment, target_id)
                assert first is not None and second is not None
                assert first.row_version == second.row_version == 1
                assert repository.update_draft_if_version(
                    first_session,
                    assessment_id=target_id,
                    owner_id=first.owner_id,
                    row_version=first.row_version,
                    values={"analysis_summary": "第一个会话"},
                    updated_at=datetime.now(timezone.utc),
                )
                first_session.commit()
                assert not repository.update_draft_if_version(
                    second_session,
                    assessment_id=target_id,
                    owner_id=second.owner_id,
                    row_version=second.row_version,
                    values={"analysis_summary": "第二个会话"},
                    updated_at=datetime.now(timezone.utc),
                )
                second_session.rollback()
            finally:
                first_session.close()
                second_session.close()

            with application.state.database.session_factory() as session:
                saved = session.get(ProductAssessment, target_id)
                assert saved is not None
                assert saved.analysis_summary == "第一个会话"
                assert saved.row_version == 2
            complete_assessment(mysql_client, target_id)
            with application.state.database.session_factory() as session:
                saved = session.get(ProductAssessment, target_id)
                assert saved is not None
                saved.status = "submitted"
                saved.submitted_by = 2
                saved.submitted_at = datetime.now(timezone.utc)
                saved.row_version = 3
                session.commit()

            approve_session = application.state.database.session_factory()
            return_session = application.state.database.session_factory()
            try:
                now = datetime.now(timezone.utc)
                assert repository.transition_if_version(
                    approve_session,
                    assessment_id=target_id,
                    expected_status="submitted",
                    row_version=3,
                    values={"status": "completed", "review_decision": "approved", "reviewer_id": 3, "reviewed_at": now},
                    updated_at=now,
                )
                approve_session.commit()
                assert not repository.transition_if_version(
                    return_session,
                    assessment_id=target_id,
                    expected_status="submitted",
                    row_version=3,
                    values={"status": "returned", "review_decision": "returned", "review_comment": "并发退回", "reviewer_id": 3, "reviewed_at": now},
                    updated_at=now,
                )
                return_session.rollback()
            finally:
                approve_session.close()
                return_session.close()

            with application.state.database.session_factory() as session:
                reviewed = session.get(ProductAssessment, target_id)
                assert reviewed is not None
                assert reviewed.status == "completed"
                assert reviewed.review_decision == "approved"
                assert reviewed.submitted_by == 2
                assert reviewed.row_version == 4

            owner = PublicUser(2, "owner", "产品负责人", ["product_owner"])
            create_barrier = Barrier(2)

            def create_revision_concurrently() -> str:
                create_barrier.wait()
                try:
                    application.state.assessment_editor_service.create_revision(
                        owner,
                        target_id,
                        AssessmentRevisionCreateRequest(
                            row_version=4, revision_reason="并发人工修订"
                        ),
                    )
                    return "created"
                except AssessmentActionConflictError:
                    return "conflict"

            with ThreadPoolExecutor(max_workers=2) as executor:
                create_results = list(executor.map(lambda _: create_revision_concurrently(), range(2)))
            assert sorted(create_results) == ["conflict", "created"]

            with application.state.database.session_factory() as session:
                completed = session.get(ProductAssessment, target_id)
                assert completed is not None
                current_id = repository.current_revision_id(
                    session,
                    product_ots_id=completed.product_ots_id,
                    vulnerability_id=completed.vulnerability_id,
                )
                assert current_id is not None and current_id != target_id
            write_barrier = Barrier(2)

            def write_current_concurrently(action: str) -> str:
                write_barrier.wait()
                try:
                    if action == "save":
                        application.state.assessment_editor_service.save_draft(
                            owner,
                            current_id,
                            AssessmentDraftUpdateRequest.model_validate(
                                draft_payload(
                                    row_version=1,
                                    analysis_summary="并发保存后的结论",
                                )
                            ),
                        )
                    else:
                        application.state.assessment_editor_service.submit(
                            owner,
                            current_id,
                            AssessmentActionRequest(row_version=1),
                        )
                    return action
                except (
                    AssessmentActionConflictError,
                    AssessmentNotEditableError,
                    AssessmentVersionConflictError,
                ):
                    return "conflict"

            with ThreadPoolExecutor(max_workers=2) as executor:
                write_results = list(
                    executor.map(write_current_concurrently, ("save", "submit"))
                )
            assert write_results.count("conflict") == 1

            submitted_target_id = assessment_id(mysql_client, "submitted")
            reviewer = PublicUser(3, "reviewer", "审核人", ["reviewer"])
            return_barrier = Barrier(2)

            def return_concurrently() -> str:
                return_barrier.wait()
                try:
                    application.state.assessment_editor_service.return_assessment(
                        reviewer,
                        submitted_target_id,
                        AssessmentReturnRequest(
                            row_version=1, review_comment="并发退回"
                        ),
                    )
                    return "returned"
                except AssessmentActionConflictError:
                    return "conflict"

            with ThreadPoolExecutor(max_workers=2) as executor:
                return_results = list(executor.map(lambda _: return_concurrently(), range(2)))
            assert sorted(return_results) == ["conflict", "returned"]

            with application.state.database.session_factory() as session:
                for business_id in (target_id, submitted_target_id):
                    root = session.get(ProductAssessment, business_id)
                    assert root is not None
                    revisions = session.scalars(
                        select(ProductAssessment).where(
                            ProductAssessment.product_ots_id == root.product_ots_id,
                            ProductAssessment.vulnerability_id == root.vulnerability_id,
                        )
                    ).all()
                    ordered = sorted(revisions, key=lambda item: item.revision_no)
                    assert sum(item.is_current for item in ordered) == 1
                    assert [item.revision_no for item in ordered] == list(
                        range(1, max(item.revision_no for item in ordered) + 1)
                    )
                    assert ordered[-1].parent_revision_id == business_id
    finally:
        if application is not None:
            application.state.database.engine.dispose()
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
