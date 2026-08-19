from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.settings import Settings
from app.main import create_app
from app.models.user import AppUser, AuditLog, Base
from app.services.authentication import AuthenticationService


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "products.db"
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
    response = client.post("/api/v1/auth/login", json={"login_name": login_name, "password": password})
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


def test_products_require_an_admin_identity(client: TestClient) -> None:
    assert client.get("/api/v1/products").status_code == 401

    AuthenticationService(client.app.state.database.session_factory).initialize_admin(
        "owner", "产品负责人", "owner-password"
    )
    with client.app.state.database.session_factory.begin() as session:
        session.scalar(select(AppUser).where(AppUser.login_name == "owner")).roles_json = ["product_owner"]
    login(client, "owner", "owner-password")

    response = client.get("/api/v1/products")

    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_FORBIDDEN"


def test_admin_can_manage_products_and_versions_with_qualified_people(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])

    created = client.post(
        "/api/v1/products",
        json={"product_code": "OTS-001", "product_name": "终端产品", "description": "第一代"},
    )
    version = client.post(
        f"/api/v1/products/{created.json()['id']}/versions",
        json={
            "version_no": "1.0",
            "description": "首个版本",
            "owner_id": owner["id"],
            "reviewer_id": reviewer["id"],
        },
    )
    page = client.get("/api/v1/products", params={"query": "终端", "status": "active"})

    assert created.status_code == 201
    assert created.json()["status"] == "active"
    assert created.json()["row_version"] == 1
    assert version.status_code == 201
    assert version.json()["primary_cvss_version"] == "3.1"
    assert version.json()["owner_id"] == owner["id"]
    assert page.status_code == 200
    assert page.json()["total"] == 1

    with client.app.state.database.session_factory() as session:
        audits = session.scalars(select(AuditLog).where(AuditLog.object_type.in_(["product", "product_version"]))).all()
        assert len(audits) == 2


def test_product_and_version_reject_duplicates_invalid_people_and_stale_updates(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    invalid = create_user(client, "invalid", ["reviewer"])
    product = client.post(
        "/api/v1/products", json={"product_code": "OTS-002", "product_name": "网关"}
    ).json()
    created_version = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={"version_no": "1.0", "owner_id": owner["id"], "reviewer_id": reviewer["id"]},
    ).json()

    duplicate_product = client.post(
        "/api/v1/products", json={"product_code": "OTS-002", "product_name": "重复"}
    )
    duplicate_version = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={"version_no": "1.0", "owner_id": owner["id"], "reviewer_id": reviewer["id"]},
    )
    invalid_owner = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={"version_no": "2.0", "owner_id": invalid["id"], "reviewer_id": reviewer["id"]},
    )
    updated = client.put(
        f"/api/v1/products/{product['id']}",
        json={"product_code": "OTS-002", "product_name": "网关（已编辑）", "description": None, "row_version": 1},
    )
    stale = client.put(
        f"/api/v1/products/{product['id']}",
        json={"product_code": "OTS-002", "product_name": "错误覆盖", "description": None, "row_version": 1},
    )

    assert duplicate_product.status_code == 409
    assert duplicate_product.json()["code"] == "PRODUCT_CODE_CONFLICT"
    assert duplicate_version.status_code == 409
    assert duplicate_version.json()["code"] == "PRODUCT_VERSION_CONFLICT"
    assert invalid_owner.status_code == 422
    assert invalid_owner.json()["code"] == "PRODUCT_ASSIGNMENT_INVALID"
    assert updated.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["code"] == "PRODUCT_VERSION_CONFLICT"
    assert created_version["row_version"] == 1


def test_disabling_product_or_version_preserves_records(client: TestClient) -> None:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product = client.post(
        "/api/v1/products", json={"product_code": "OTS-003", "product_name": "控制器"}
    ).json()
    version = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={"version_no": "1.0", "owner_id": owner["id"], "reviewer_id": reviewer["id"]},
    ).json()

    disabled_version = client.post(f"/api/v1/products/{product['id']}/versions/{version['id']}/disable", json={"row_version": 1})
    disabled_product = client.post(f"/api/v1/products/{product['id']}/disable", json={"row_version": 1})

    assert disabled_version.status_code == 200
    assert disabled_version.json()["status"] == "disabled"
    assert disabled_product.status_code == 200
    assert disabled_product.json()["status"] == "disabled"
    assert client.get(f"/api/v1/products/{product['id']}/versions/{version['id']}").status_code == 200
