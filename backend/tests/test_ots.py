from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.main import create_app
from app.models.user import AppUser, AuditLog, Base
from app.services.authentication import AuthenticationService


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "ots.db"
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
    assert client.post("/api/v1/auth/login", json={"login_name": login_name, "password": password}).status_code == 200


def create_version(client: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    owner = client.post("/api/v1/users", json={"login_name": "owner", "display_name": "负责人", "password": "password", "roles": ["product_owner"]}).json()
    reviewer = client.post("/api/v1/users", json={"login_name": "reviewer", "display_name": "审核人", "password": "password", "roles": ["reviewer"]}).json()
    product = client.post("/api/v1/products", json={"product_code": "P-001", "product_name": "测试产品"}).json()
    version = client.post(f"/api/v1/products/{product['id']}/versions", json={"version_no": "1.0", "owner_id": owner["id"], "reviewer_id": reviewer["id"]}).json()
    return product, version


def test_ots_requires_admin_and_has_no_disable_or_delete(client: TestClient) -> None:
    assert client.get("/api/v1/ots-components").status_code == 401
    AuthenticationService(client.app.state.database.session_factory).initialize_admin("owner", "负责人", "owner-password")
    with client.app.state.database.session_factory.begin() as session:
        session.scalar(select(AppUser).where(AppUser.login_name == "owner")).roles_json = ["product_owner"]
    login(client, "owner", "owner-password")
    assert client.get("/api/v1/ots-components").status_code == 403

    login(client)
    created = client.post("/api/v1/ots-components", json={"ots_name": " OpenSSL ", "ots_version": " 3.0.0 ", "official_website": "https://openssl.org", "is_eol": False})
    assert created.status_code == 201
    assert created.json()["ots_name"] == "OpenSSL"
    assert "status" not in created.json()
    assert client.post(f"/api/v1/ots-components/{created.json()['id']}/disable", json={"row_version": 1}).status_code == 404
    assert client.delete(f"/api/v1/ots-components/{created.json()['id']}").status_code == 405


def test_ots_unique_key_filters_and_optimistic_lock(client: TestClient) -> None:
    login(client)
    created = client.post("/api/v1/ots-components", json={"ots_name": "OpenSSL", "ots_version": "3.0.0", "official_website": "https://openssl.org", "is_eol": False}).json()
    duplicate = client.post("/api/v1/ots-components", json={"ots_name": " OpenSSL ", "ots_version": "3.0.0 ", "official_website": "https://example.test", "is_eol": True})
    page = client.get("/api/v1/ots-components", params={"query": "SSL", "is_eol": False})
    updated = client.put(f"/api/v1/ots-components/{created['id']}", json={"ots_name": "OpenSSL", "ots_version": "3.0.0", "official_website": "https://www.openssl.org", "is_eol": False, "row_version": 1})
    stale = client.put(f"/api/v1/ots-components/{created['id']}", json={"ots_name": "OpenSSL", "ots_version": "3.0.0", "official_website": "https://stale.test", "is_eol": True, "row_version": 1})

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "OTS_COMPONENT_CONFLICT"
    assert page.json()["total"] == 1
    assert updated.json()["row_version"] == 2
    assert stale.status_code == 409
    assert stale.json()["code"] == "OTS_VERSION_CONFLICT"


def test_product_ots_relations_export_and_audit(client: TestClient) -> None:
    login(client)
    product, version = create_version(client)
    ots = client.post("/api/v1/ots-components", json={"ots_name": "zlib", "ots_version": "1.3", "official_website": "https://zlib.net", "is_eol": False}).json()
    relation = client.post(f"/api/v1/product-versions/{version['id']}/ots", json={"ots_component_id": ots["id"]})
    duplicate = client.post(f"/api/v1/product-versions/{version['id']}/ots", json={"ots_component_id": ots["id"]})
    listing = client.get(f"/api/v1/product-versions/{version['id']}/ots")
    reverse = client.get(f"/api/v1/ots-components/{ots['id']}/product-versions")
    exported = client.get(f"/api/v1/product-versions/{version['id']}/ots/export")

    assert relation.status_code == 201
    assert relation.json()["created_by"] == 1
    assert duplicate.status_code == 409
    assert listing.json()[0]["ots_name"] == "zlib"
    assert reverse.json()[0]["product_name"] == product["product_name"]
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.text.splitlines() == ["ots_name,ots_version,official_website,is_eol", "zlib,1.3,https://zlib.net,false"]

    before = client.get("/api/v1/product-ots/template")
    assert before.text.splitlines()[0] == "ots_name,ots_version,official_website,is_eol"
    with client.app.state.database.session_factory() as session:
        audits = session.scalars(select(AuditLog).where(AuditLog.object_type == "product_ots")).all()
        assert len(audits) == 1

    removed = client.delete(f"/api/v1/product-versions/{version['id']}/ots/{relation.json()['id']}")
    assert removed.status_code == 204
    assert client.get(f"/api/v1/ots-components/{ots['id']}").status_code == 200
    assert client.get(f"/api/v1/product-versions/{version['id']}/ots").json() == []


def test_csv_import_is_atomic_idempotent_and_reports_fields(client: TestClient) -> None:
    login(client)
    _, version = create_version(client)
    headers = {"content-type": "text/csv; charset=utf-8", "x-file-name": "bom.csv"}
    valid = "ots_name,ots_version,official_website,is_eol\nOpenSSL,3.0.0,https://openssl.org,false\nzlib,1.3,https://zlib.net,false\n"
    first = client.post(f"/api/v1/product-versions/{version['id']}/ots/import", content=valid.encode(), headers=headers)
    second = client.post(f"/api/v1/product-versions/{version['id']}/ots/import", content=valid.encode(), headers=headers)
    conflict = "ots_name,ots_version,official_website,is_eol\nOpenSSL,3.0.0,https://conflict.test,true\nnew,1.0,https://new.test,false\n"
    failed = client.post(f"/api/v1/product-versions/{version['id']}/ots/import", content=conflict.encode(), headers=headers)

    assert first.status_code == 200
    assert first.json() == {"created_ots": 2, "created_relations": 2, "existing_relations": 0}
    assert second.json() == {"created_ots": 0, "created_relations": 0, "existing_relations": 2}
    assert failed.status_code == 422
    assert {item["field"] for item in failed.json()["errors"]} == {"official_website", "is_eol"}
    assert all(item["row"] == 2 for item in failed.json()["errors"])
    assert client.get("/api/v1/ots-components", params={"query": "new"}).json()["total"] == 0


def test_relation_with_downstream_history_cannot_be_removed(client: TestClient) -> None:
    login(client)
    _, version = create_version(client)
    ots = client.post("/api/v1/ots-components", json={"ots_name": "busybox", "ots_version": "1.36", "official_website": "https://busybox.net", "is_eol": False}).json()
    relation = client.post(f"/api/v1/product-versions/{version['id']}/ots", json={"ots_component_id": ots["id"]}).json()
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text("CREATE TABLE product_assessment (id INTEGER PRIMARY KEY, product_ots_id INTEGER NOT NULL)"))
        connection.execute(text("INSERT INTO product_assessment (id, product_ots_id) VALUES (1, :relation_id)"), {"relation_id": relation["id"]})

    protected = client.delete(f"/api/v1/product-versions/{version['id']}/ots/{relation['id']}")
    assert protected.status_code == 409
    assert protected.json()["code"] == "PRODUCT_OTS_HISTORY_CONFLICT"


def test_csv_rejects_bad_headers_duplicate_keys_and_extra_columns_without_writes(client: TestClient) -> None:
    login(client)
    _, version = create_version(client)
    headers = {"content-type": "text/csv; charset=utf-8", "x-file-name": "bad.csv"}
    bad_header = client.post(f"/api/v1/product-versions/{version['id']}/ots/import", content=b"name,version\nOpenSSL,3.0\n", headers=headers)
    duplicate_and_extra = "ots_name,ots_version,official_website,is_eol\nOpenSSL,3.0,https://openssl.org,false\nOpenSSL,3.0,https://openssl.org,false,extra\n"
    bad_rows = client.post(f"/api/v1/product-versions/{version['id']}/ots/import", content=duplicate_and_extra.encode(), headers=headers)

    assert bad_header.status_code == 422
    assert bad_header.json()["errors"][0]["field"] == "header"
    assert bad_rows.status_code == 422
    assert {error["field"] for error in bad_rows.json()["errors"]} == {"row", "ots_name"}
    assert client.get("/api/v1/ots-components").json()["total"] == 0
