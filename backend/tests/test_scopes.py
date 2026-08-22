from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.infrastructure.settings import Settings
from app.main import create_app
from app.migrations import apply_migrations
from app.models.scopes import UserProductScope
from app.models.user import AuditLog, Base
from app.services.authentication import AuthenticationService, PublicUser
from app.services.scopes import ProductScopeForbiddenError, ScopeAuthorizationService


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "scopes.db"
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


def create_user(client: TestClient, login_name: str, roles: list[str]) -> dict[str, object]:
    response = client.post(
        "/api/v1/users",
        json={
            "login_name": login_name,
            "display_name": login_name,
            "password": "user-password",
            "roles": roles,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_product_with_versions(
    client: TestClient,
    code: str,
    owner_id: int,
    reviewer_id: int,
    versions: tuple[str, ...] = ("1.0",),
) -> tuple[dict[str, object], list[dict[str, object]]]:
    product = client.post(
        "/api/v1/products",
        json={"product_code": code, "product_name": f"产品 {code}"},
    ).json()
    created_versions = [
        client.post(
            f"/api/v1/products/{product['id']}/versions",
            json={
                "version_no": version_no,
                "owner_id": owner_id,
                "reviewer_id": reviewer_id,
            },
        ).json()
        for version_no in versions
    ]
    return product, created_versions


def grant_scope(
    client: TestClient,
    user_id: int,
    scope_type: str,
    product_id: int,
    product_version_id: int | None = None,
) -> Response:
    return client.post(
        f"/api/v1/users/{user_id}/scopes",
        json={
            "scope_type": scope_type,
            "product_id": product_id,
            "product_version_id": product_version_id,
        },
    )


def test_admin_grants_lists_and_revokes_scopes_with_idempotent_audit(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product, versions = create_product_with_versions(client, "P-001", owner["id"], reviewer["id"], ("1.0", "2.0"))

    granted = grant_scope(client, owner["id"], "product", product["id"])
    duplicate = grant_scope(client, owner["id"], "product", product["id"])
    summary = client.get(f"/api/v1/users/{owner['id']}/scopes")

    assert granted.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == granted.json()["id"]
    assert summary.status_code == 200
    assert summary.json()["is_global"] is False
    assert summary.json()["effective_product_ids"] == [product["id"]]
    assert summary.json()["effective_version_ids"] == [version["id"] for version in versions]
    assert summary.json()["scopes"][0]["scope_key"] == f"product:{product['id']}"

    removed = client.delete(f"/api/v1/users/{owner['id']}/scopes/{granted.json()['id']}")
    removed_again = client.delete(f"/api/v1/users/{owner['id']}/scopes/{granted.json()['id']}")

    assert removed.status_code == 204
    assert removed_again.status_code == 204
    assert client.get(f"/api/v1/users/{owner['id']}/scopes").json()["scopes"] == []
    with client.app.state.database.session_factory() as session:
        audits = session.scalars(
            select(AuditLog)
            .where(AuditLog.object_type == "user_product_scope")
            .order_by(AuditLog.id)
        ).all()
        assert [audit.action for audit in audits] == ["insert", "delete"]
        assert audits[0].detail_json["target_user_id"] == owner["id"]


def test_scope_validation_and_admin_only_management(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product_a, _ = create_product_with_versions(client, "P-101", owner["id"], reviewer["id"])
    product_b, versions_b = create_product_with_versions(client, "P-102", owner["id"], reviewer["id"])

    mismatched = grant_scope(client, owner["id"], "version", product_a["id"], versions_b[0]["id"])
    invalid_type = grant_scope(client, owner["id"], "tenant", product_b["id"])

    assert mismatched.status_code == 422
    assert mismatched.json()["code"] == "PRODUCT_SCOPE_INVALID"
    assert invalid_type.status_code == 422

    login(client, "owner", "user-password")
    forbidden = client.get(f"/api/v1/users/{owner['id']}/scopes")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"


def test_product_and_version_scopes_filter_reads_and_block_direct_writes(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product_a, versions_a = create_product_with_versions(client, "P-201", owner["id"], reviewer["id"], ("1.0", "2.0"))
    product_b, versions_b = create_product_with_versions(client, "P-202", owner["id"], reviewer["id"])
    ots = client.post(
        "/api/v1/ots-components",
        json={"ots_name": "zlib", "ots_version": "1.3", "official_website": "https://zlib.net", "is_eol": False},
    ).json()
    client.post(
        f"/api/v1/product-versions/{versions_a[0]['id']}/ots",
        json={"ots_component_id": ots["id"]},
    )
    assert grant_scope(client, owner["id"], "version", product_a["id"], versions_a[0]["id"]).status_code == 200

    login(client, "owner", "user-password")
    products = client.get("/api/v1/products")
    versions = client.get(f"/api/v1/products/{product_a['id']}/versions")
    allowed_ots = client.get(f"/api/v1/product-versions/{versions_a[0]['id']}/ots")
    forbidden_version = client.get(f"/api/v1/products/{product_a['id']}/versions/{versions_a[1]['id']}")
    forbidden_product = client.get(f"/api/v1/products/{product_b['id']}")
    forbidden_ots = client.get(f"/api/v1/product-versions/{versions_b[0]['id']}/ots")
    forbidden_write = client.put(
        f"/api/v1/products/{product_a['id']}",
        json={
            "product_code": product_a["product_code"],
            "product_name": "越权修改",
            "description": None,
            "row_version": product_a["row_version"],
        },
    )

    assert products.status_code == 200
    assert products.json()["total"] == 1
    assert [item["id"] for item in products.json()["items"]] == [product_a["id"]]
    assert [item["id"] for item in versions.json()] == [versions_a[0]["id"]]
    assert allowed_ots.status_code == 200
    assert allowed_ots.json()[0]["ots_name"] == "zlib"
    for response in (forbidden_version, forbidden_product, forbidden_ots):
        assert response.status_code == 403
        assert response.json()["code"] == "PRODUCT_SCOPE_FORBIDDEN"
    assert forbidden_write.status_code == 403
    assert forbidden_write.json()["code"] == "AUTH_FORBIDDEN"


def test_product_scope_vertical_flow_covers_versions_and_ots_then_revokes_access(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product, versions = create_product_with_versions(
        client, "P-250", owner["id"], reviewer["id"], ("1.0", "2.0")
    )
    ots = client.post(
        "/api/v1/ots-components",
        json={"ots_name": "OpenSSL", "ots_version": "3.0", "official_website": "https://openssl.org", "is_eol": False},
    ).json()
    client.post(
        f"/api/v1/product-versions/{versions[1]['id']}/ots",
        json={"ots_component_id": ots["id"]},
    )
    granted = grant_scope(client, owner["id"], "product", product["id"])
    assert granted.status_code == 200

    login(client, "owner", "user-password")
    assert [
        version["id"]
        for version in client.get(f"/api/v1/products/{product['id']}/versions").json()
    ] == [version["id"] for version in versions]
    assert client.get(f"/api/v1/product-versions/{versions[1]['id']}/ots").json()[0]["ots_name"] == "OpenSSL"

    login(client)
    assert client.delete(
        f"/api/v1/users/{owner['id']}/scopes/{granted.json()['id']}"
    ).status_code == 204
    login(client, "owner", "user-password")
    denied = client.get(f"/api/v1/products/{product['id']}")
    assert denied.status_code == 403
    assert denied.json()["code"] == "PRODUCT_SCOPE_FORBIDDEN"


def test_admin_is_global_and_disabled_targets_make_explicit_scopes_ineffective(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product, versions = create_product_with_versions(client, "P-301", owner["id"], reviewer["id"])
    granted = grant_scope(client, owner["id"], "version", product["id"], versions[0]["id"])
    assert granted.status_code == 200

    admin_summary = client.get("/api/v1/scopes/me")
    assert admin_summary.status_code == 200
    assert admin_summary.json() == {
        "is_global": True,
        "scopes": [],
        "effective_product_ids": [],
        "effective_version_ids": [],
    }

    disabled = client.post(
        f"/api/v1/products/{product['id']}/versions/{versions[0]['id']}/disable",
        json={"row_version": 1},
    )
    assert disabled.status_code == 200
    login(client, "owner", "user-password")
    summary = client.get("/api/v1/scopes/me")

    assert summary.status_code == 200
    assert summary.json()["effective_product_ids"] == []
    assert summary.json()["effective_version_ids"] == []
    assert summary.json()["scopes"][0]["is_effective"] is False
    forbidden = client.get(f"/api/v1/products/{product['id']}/versions/{versions[0]['id']}")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "PRODUCT_SCOPE_FORBIDDEN"


def test_scope_audit_failure_rolls_back_the_grant(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product, _ = create_product_with_versions(client, "P-401", owner["id"], reviewer["id"])

    def fail_scope_audit(session: Session, _flush_context, _instances) -> None:
        if any(
            isinstance(item, AuditLog) and item.object_type == "user_product_scope"
            for item in session.new
        ):
            raise RuntimeError("audit unavailable")

    event.listen(Session, "before_flush", fail_scope_audit)
    try:
        response = grant_scope(client, owner["id"], "product", product["id"])
    finally:
        event.remove(Session, "before_flush", fail_scope_audit)

    assert response.status_code == 500
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(UserProductScope)) is None
        assert session.scalar(
            select(AuditLog).where(AuditLog.object_type == "user_product_scope")
        ) is None


def test_assignment_rules_are_composable_and_admin_does_not_bypass_them() -> None:
    admin = PublicUser(1, "admin", "管理员", ["admin"])
    reviewer = PublicUser(2, "reviewer", "审核人", ["reviewer"])

    with pytest.raises(ProductScopeForbiddenError):
        ScopeAuthorizationService.require_assigned_role(
            admin,
            required_role="reviewer",
            assigned_user_id=1,
        )
    ScopeAuthorizationService.require_assigned_role(
        reviewer,
        required_role="reviewer",
        assigned_user_id=2,
    )
    with pytest.raises(ProductScopeForbiddenError):
        ScopeAuthorizationService.require_assigned_role(
            reviewer,
            required_role="reviewer",
            assigned_user_id=2,
            submitted_by=2,
            forbid_self_review=True,
        )


def test_mysql_scope_migration_and_audit_commit_together(monkeypatch) -> None:
    configured_url = Settings.from_environment().database_url
    assert configured_url is not None
    url = make_url(configured_url)
    database_name = f"ots05_test_{uuid4().hex}"
    admin_engine = create_engine(url.set(database="mysql"))
    test_engine = None
    application = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"))
        test_url = url.set(database=database_name)
        test_engine = create_engine(test_url)
        versions = apply_migrations(test_engine, Path(__file__).parents[1] / "migrations")
        assert versions == list(range(1, 10))
        monkeypatch.setenv("OTS_DATABASE_URL", test_url.render_as_string(hide_password=False))
        application = create_app()
        AuthenticationService(application.state.database.session_factory).initialize_admin(
            "admin", "初始管理员", "admin-password"
        )
        with TestClient(application, raise_server_exceptions=False) as mysql_client:
            login(mysql_client)
            owner = create_user(mysql_client, "mysql-owner", ["product_owner"])
            reviewer = create_user(mysql_client, "mysql-reviewer", ["reviewer"])
            product, _ = create_product_with_versions(
                mysql_client, "MYSQL-P-001", owner["id"], reviewer["id"]
            )
            granted = grant_scope(mysql_client, owner["id"], "product", product["id"])
            assert granted.status_code == 200

        with pytest.raises(DBAPIError):
            with test_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO user_product_scope "
                        "(user_id, scope_type, product_id, product_version_id, scope_key, created_by) "
                        "VALUES (:user_id, 'product', :product_id, :version_id, 'invalid', 1)"
                    ),
                    {
                        "user_id": owner["id"],
                        "product_id": product["id"],
                        "version_id": 1,
                    },
                )
        with pytest.raises(DBAPIError):
            with test_engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM product WHERE id = :product_id"),
                    {"product_id": product["id"]},
                )

        with application.state.database.session_factory() as session:
            scope_count = session.scalar(text("SELECT COUNT(*) FROM user_product_scope"))
            audit_count = session.scalar(
                select(AuditLog).where(AuditLog.object_type == "user_product_scope").with_only_columns(text("COUNT(*)"))
            )
            assert scope_count == 1
            assert audit_count == 1
    finally:
        if application is not None:
            application.state.database.engine.dispose()
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
