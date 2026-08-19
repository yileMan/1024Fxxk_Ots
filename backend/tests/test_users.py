from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.infrastructure.settings import Settings
from app.main import create_app
from app.migrations import apply_migrations
from app.models.user import AppUser, AuditLog, Base
from app.services.authentication import AuthenticationService


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "users.db"
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{database_path}")
    application = create_app()
    Base.metadata.create_all(application.state.database.engine)
    AuthenticationService(application.state.database.session_factory).initialize_admin(
        "admin", "初始管理员", "admin-password"
    )
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client
    application.state.database.engine.dispose()


def login(client: TestClient, login_name: str = "admin", password: str = "admin-password") -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": login_name, "password": password},
    )
    assert response.status_code == 200


def test_users_require_an_admin_identity(client: TestClient) -> None:
    assert client.get("/api/v1/users").status_code == 401

    AuthenticationService(client.app.state.database.session_factory).initialize_admin(
        "owner", "产品负责人", "owner-password"
    )
    with client.app.state.database.session_factory.begin() as session:
        session.scalar(select(AppUser).where(AppUser.login_name == "owner")).roles_json = [
            "product_owner"
        ]
    login(client, "owner", "owner-password")

    response = client.get("/api/v1/users")

    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_FORBIDDEN"
    assert "password" not in response.text.lower()


def test_admin_can_create_filter_and_page_users_without_exposing_secrets(client: TestClient) -> None:
    login(client)

    created = client.post(
        "/api/v1/users",
        json={
            "login_name": "zhangsan",
            "display_name": "张三",
            "password": "plain-secret",
            "roles": ["reviewer", "product_owner"],
        },
    )
    duplicate = client.post(
        "/api/v1/users",
        json={
            "login_name": "zhangsan",
            "display_name": "重复用户",
            "password": "another-secret",
            "roles": ["reviewer"],
        },
    )
    invalid_role = client.post(
        "/api/v1/users",
        json={
            "login_name": "invalid",
            "display_name": "无效角色",
            "password": "secret",
            "roles": ["root"],
        },
    )
    page = client.get("/api/v1/users", params={"query": "张", "role": "reviewer", "page": 1, "page_size": 1})

    assert created.status_code == 201
    assert created.json()["roles"] == ["reviewer", "product_owner"]
    assert created.json()["status"] == "active"
    assert created.json()["row_version"] == 1
    assert "password" not in created.text.lower()
    assert "plain-secret" not in created.text
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "USER_LOGIN_NAME_CONFLICT"
    assert invalid_role.status_code == 422
    assert invalid_role.json()["code"] == "VALIDATION_ERROR"
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert [item["login_name"] for item in page.json()["items"]] == ["zhangsan"]

    with client.app.state.database.session_factory() as session:
        audits = session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
        assert len(audits) == 1
        assert audits[0].action == "insert"
        assert audits[0].object_type == "app_user"
        assert "password" not in str(audits[0].detail_json).lower()
        assert "plain-secret" not in str(audits[0].detail_json)


def test_edit_reset_and_disable_use_optimistic_locking_and_safe_audit(client: TestClient) -> None:
    login(client)
    created = client.post(
        "/api/v1/users",
        json={
            "login_name": "lisi",
            "display_name": "李四",
            "password": "old-secret",
            "roles": ["reviewer"],
        },
    ).json()

    updated = client.put(
        f"/api/v1/users/{created['id']}",
        json={"display_name": "李四（审核）", "roles": ["reviewer", "admin"], "row_version": 1},
    )
    stale = client.put(
        f"/api/v1/users/{created['id']}",
        json={"display_name": "被覆盖的名称", "roles": ["admin"], "row_version": 1},
    )
    reset = client.post(
        f"/api/v1/users/{created['id']}/reset-password",
        json={"password": "new-secret", "row_version": 2},
    )
    disabled = client.post(
        f"/api/v1/users/{created['id']}/disable",
        json={"row_version": 3},
    )
    disabled_again = client.post(
        f"/api/v1/users/{created['id']}/disable",
        json={"row_version": 4},
    )

    assert updated.status_code == 200
    assert updated.json()["row_version"] == 2
    assert stale.status_code == 409
    assert stale.json()["code"] == "USER_VERSION_CONFLICT"
    assert reset.status_code == 200
    assert reset.json()["row_version"] == 3
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["row_version"] == 4
    assert disabled_again.status_code == 200
    assert disabled_again.json()["row_version"] == 4

    client.cookies.clear()
    login(client, "lisi", "new-secret")

    with client.app.state.database.session_factory() as session:
        user = session.get(AppUser, created["id"])
        audits = session.scalars(
            select(AuditLog).where(AuditLog.object_id == str(created["id"])).order_by(AuditLog.id)
        ).all()
        assert user.display_name == "李四（审核）"
        assert len(audits) == 4
        assert audits[-2].detail_json["password_reset"] is True
        assert "new-secret" not in str([audit.detail_json for audit in audits])
        assert "password_hash" not in str([audit.detail_json for audit in audits])


def test_audit_failure_rolls_back_the_user_change(client: TestClient) -> None:
    login(client)

    def fail_audit(session: Session, _flush_context, _instances) -> None:
        if any(isinstance(item, AuditLog) for item in session.new):
            raise RuntimeError("audit unavailable")

    event.listen(Session, "before_flush", fail_audit)
    try:
        response = client.post(
            "/api/v1/users",
            json={
                "login_name": "rollback-user",
                "display_name": "回滚用户",
                "password": "secret",
                "roles": ["reviewer"],
            },
        )
    finally:
        event.remove(Session, "before_flush", fail_audit)

    assert response.status_code == 500
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(AppUser).where(AppUser.login_name == "rollback-user")) is None
        assert session.scalar(select(AuditLog).where(AuditLog.object_type == "app_user")) is None


def test_mysql_user_change_and_audit_are_committed_together(monkeypatch) -> None:
    configured_url = Settings.from_environment().database_url
    assert configured_url is not None
    url = make_url(configured_url)
    database_name = f"ots02_test_{uuid4().hex}"
    admin_engine = create_engine(url.set(database="mysql"))
    test_engine = None
    application = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"))
        test_url = url.set(database=database_name)
        test_engine = create_engine(test_url)
        apply_migrations(test_engine, Path(__file__).parents[1] / "migrations")
        monkeypatch.setenv("OTS_DATABASE_URL", test_url.render_as_string(hide_password=False))
        application = create_app()
        AuthenticationService(application.state.database.session_factory).initialize_admin(
            "admin", "初始管理员", "admin-password"
        )
        with TestClient(application) as mysql_client:
            login(mysql_client)
            response = mysql_client.post(
                "/api/v1/users",
                json={
                    "login_name": "mysql-user",
                    "display_name": "MySQL 用户",
                    "password": "secret",
                    "roles": ["product_owner"],
                },
            )
        assert response.status_code == 201
        with application.state.database.session_factory() as session:
            user = session.scalar(select(AppUser).where(AppUser.login_name == "mysql-user"))
            audit = session.scalar(select(AuditLog).where(AuditLog.object_id == str(user.id)))
            assert audit.user_id == 1
            assert audit.action == "insert"
    finally:
        if application is not None:
            application.state.database.engine.dispose()
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
