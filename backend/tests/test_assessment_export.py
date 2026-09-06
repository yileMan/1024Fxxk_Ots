from __future__ import annotations

import csv
from io import StringIO

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.assessments import ProductAssessment
from app.models.user import AuditLog
from test_vulnerability_workbench import client, login, seed_catalog  # noqa: F401


EXPECTED_HEADERS = [
    "产品", "产品版本", "OTS 名称", "OTS 版本", "CVE", "来源评分", "来源向量",
    "环境评分", "环境向量", "适用性", "分析依据", "处置建议", "评估状态",
    "提交人", "提交时间", "审核结论", "审核人", "审核时间", "审核意见",
]


def test_preview_and_csv_export_current_assessments(client: TestClient) -> None:
    scope = seed_catalog(client)
    version_id = int(scope["version_a"]["id"])
    ots_id = int(scope["ots_a"]["id"])

    preview = client.get(
        "/api/v1/assessment-exports/preview",
        params={"product_version_id": version_id, "ots_id": ots_id},
    )
    assert preview.status_code == 200
    assert preview.json()["row_count"] == 4

    before_audit = _audit_count(client)
    response = client.get(
        "/api/v1/assessment-exports/csv",
        params={"product_version_id": version_id, "ots_id": ots_id},
    )
    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "text/csv" in response.headers["content-type"]
    assert "assessment_export_pv-" in response.headers["content-disposition"]
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"), newline="")))
    assert rows[0] == EXPECTED_HEADERS
    assert [row[4] for row in rows[1:]] == sorted(row[4] for row in rows[1:])
    assert len(rows) == 5
    assert _audit_count(client) == before_audit


def test_export_authorization_relationship_and_empty_scope(client: TestClient) -> None:
    scope = seed_catalog(client)
    version_a = int(scope["version_a"]["id"])
    version_b = int(scope["version_b"]["id"])
    ots_a = int(scope["ots_a"]["id"])
    ots_b = int(scope["ots_b"]["id"])

    assert client.get("/api/v1/assessment-exports/preview").status_code == 422
    assert client.get(
        "/api/v1/assessment-exports/preview",
        params={"product_version_id": version_a, "ots_id": ots_b},
    ).status_code == 404

    client.cookies.clear()
    login(client, "owner", "user-password")
    forbidden = client.get(
        "/api/v1/assessment-exports/preview",
        params={"product_version_id": version_b, "ots_id": ots_b},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ASSESSMENT_EXPORT_FORBIDDEN"

    allowed = client.get(
        "/api/v1/assessment-exports/preview",
        params={"product_version_id": version_a, "ots_id": ots_a},
    )
    assert allowed.status_code == 200


def test_csv_rejects_empty_export(client: TestClient) -> None:
    scope = seed_catalog(client)
    with client.app.state.database.session_factory.begin() as session:
        session.query(ProductAssessment).delete()
    response = client.get(
        "/api/v1/assessment-exports/csv",
        params={
            "product_version_id": scope["version_a"]["id"],
            "ots_id": scope["ots_a"]["id"],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ASSESSMENT_EXPORT_EMPTY"


def _audit_count(client: TestClient) -> int:
    with client.app.state.database.session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(AuditLog)) or 0)
