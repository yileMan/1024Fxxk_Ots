from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models.user import AppUser, AuditLog, Base
from app.services.authentication import AuthenticationService
from app.services.audit import normalize_audit_detail, record_audit


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "audit-operations.db"
    backup_status = tmp_path / "backup-status-v1.json"
    backup_status.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "status": "success",
                "started_at": "2026-09-06T01:00:00Z",
                "finished_at": "2026-09-06T01:02:00Z",
                "file_name": "ots-20260906.sql.gz",
                "size_bytes": 1024,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("OTS_APP_VERSION", "1.0.0-test")
    monkeypatch.setenv("OTS_PERSISTENT_ROOT", str(tmp_path))
    monkeypatch.setenv("OTS_BACKUP_STATUS_FILE", str(backup_status))
    application = create_app()
    Base.metadata.create_all(application.state.database.engine)
    authentication = AuthenticationService(application.state.database.session_factory)
    authentication.initialize_admin("admin", "管理员", "admin-password")
    authentication.initialize_admin("owner", "负责人", "owner-password")
    with application.state.database.session_factory.begin() as session:
        owner = session.scalar(select(AppUser).where(AppUser.login_name == "owner"))
        assert owner is not None
        owner.roles_json = ["product_owner"]
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client
    application.state.database.engine.dispose()


def login(client: TestClient, name: str = "admin", password: str = "admin-password") -> None:
    assert client.post(
        "/api/v1/auth/login", json={"login_name": name, "password": password}
    ).status_code == 200


def seed_audits(client: TestClient) -> None:
    with client.app.state.database.session_factory.begin() as session:
        admin = session.scalar(select(AppUser).where(AppUser.login_name == "admin"))
        assert admin is not None
        moment = datetime(2026, 9, 6, 2, 0, tzinfo=UTC)
        session.add_all(
            [
                AuditLog(
                    user_id=admin.id,
                    action="update",
                    object_type="product",
                    object_id="8",
                    detail_json={
                        "schema_version": "1.0",
                        "changes": {"product_name": {"from": "旧名称", "to": "<新名称>"}},
                    },
                    created_at=moment,
                ),
                AuditLog(
                    user_id=None,
                    action="batch_upsert",
                    object_type="vulnerability",
                    object_id=None,
                    detail_json={"batch_no": "B-1", "new": 2},
                    created_at=moment,
                ),
                AuditLog(
                    user_id=admin.id,
                    action="insert",
                    object_type="product",
                    object_id="9",
                    detail_json={"product_code": "P-9"},
                    created_at=moment - timedelta(days=1),
                ),
            ]
        )


def test_audit_endpoints_require_admin_without_existence_leak(client: TestClient) -> None:
    assert client.get("/api/v1/audit-logs").status_code == 401
    login(client, "owner", "owner-password")
    assert client.get("/api/v1/audit-logs").status_code == 403
    assert client.get("/api/v1/audit-logs/999999").status_code == 403


def test_admin_filters_pages_and_reads_audit_detail_without_writing_audit(client: TestClient) -> None:
    seed_audits(client)
    login(client)
    with client.app.state.database.session_factory() as session:
        before = int(session.scalar(select(func.count(AuditLog.id))) or 0)

    first = client.get(
        "/api/v1/audit-logs",
        params={"object_type": "product", "action": "update", "limit": 1},
    )
    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["actor_display_name"] == "管理员"
    assert body["items"][0]["detail_keys"] == ["changes", "schema_version"]

    detail = client.get(f"/api/v1/audit-logs/{body['items'][0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["detail"]["changes"]["product_name"]["to"] == "<新名称>"
    with client.app.state.database.session_factory() as session:
        assert int(session.scalar(select(func.count(AuditLog.id))) or 0) == before


def test_audit_query_validates_ranges_and_whitelists(client: TestClient) -> None:
    login(client)
    assert client.get("/api/v1/audit-logs", params={"action": "login"}).status_code == 422
    assert client.get("/api/v1/audit-logs", params={"object_type": "unknown"}).status_code == 422
    assert client.get("/api/v1/audit-logs", params={"cursor": "%%%"}).status_code == 422
    assert client.get(
        "/api/v1/audit-logs",
        params={
            "created_from": "2026-09-07T00:00:00Z",
            "created_to": "2026-09-06T00:00:00Z",
        },
    ).status_code == 422


def test_system_operations_is_admin_only_partial_and_read_only(client: TestClient, monkeypatch) -> None:
    assert client.get("/api/v1/system/operations").status_code == 401
    login(client, "owner", "owner-password")
    assert client.get("/api/v1/system/operations").status_code == 403
    login(client)
    with client.app.state.database.session_factory() as session:
        before = int(session.scalar(select(func.count(AuditLog.id))) or 0)

    response = client.get("/api/v1/system/operations")
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {
        "overall_status", "observed_at", "application", "database", "disk",
        "backup", "latest_import", "latest_failure",
    }
    assert body["application"]["version"] == "1.0.0-test"
    assert body["database"]["status"] == "ok"
    assert body["backup"]["file_name"] == "ots-20260906.sql.gz"
    assert str(client.app.state.settings.persistent_root) not in response.text
    with client.app.state.database.session_factory() as session:
        assert int(session.scalar(select(func.count(AuditLog.id))) or 0) == before

    monkeypatch.setattr(client.app.state.system_operations_service, "_database", lambda _: (_ for _ in ()).throw(RuntimeError("secret-dsn")))
    degraded = client.get("/api/v1/system/operations")
    assert degraded.status_code == 200
    assert degraded.json()["database"]["status"] == "error"
    assert "secret-dsn" not in degraded.text


def test_invalid_backup_status_is_reported_without_leaking_contents(client: TestClient) -> None:
    login(client)
    client.app.state.settings.backup_status_file.write_text(
        '{"schema_version":"9","password":"secret"}', encoding="utf-8"
    )
    response = client.get("/api/v1/system/operations")
    assert response.status_code == 200
    assert response.json()["backup"]["status"] == "error"
    assert "secret" not in response.text


def test_public_health_remains_minimal(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(client.app.state.database, "check", lambda: True)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"service": "available", "database": "available"}
    assert "backup" not in response.text


def test_unified_audit_contract_rejects_actions_and_sanitizes_leaf_values(client: TestClient) -> None:
    detail = normalize_audit_detail({
        "password": "plain-secret",
        "changes": {"review_comment": {"from": {"length": 2}, "to": {"length": 4}}},
        "large": "x" * 1001,
    })
    assert detail is not None and detail["schema_version"] == "1.0"
    assert detail["password"] == {"changed": True}
    assert detail["changes"]["review_comment"]["to"]["length"] == 4
    assert detail["large"] == {"changed": True, "length": 1001}
    with client.app.state.database.session_factory.begin() as session:
        with pytest.raises(ValueError, match="审计动作"):
            record_audit(
                session, user_id=None, action="login", object_type="app_user",
                object_id=None, detail=None,
            )
