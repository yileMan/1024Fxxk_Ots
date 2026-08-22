from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models.imports import ImportBatch
from app.models.ots import OtsComponent, ProductOts
from app.models.user import AuditLog, Base
from app.services.authentication import AuthenticationService


@pytest.fixture
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "collector-scope.db"
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


def create_product_version(
    client: TestClient,
    *,
    code: str,
    version_no: str,
    owner_id: int,
    reviewer_id: int,
) -> tuple[dict[str, object], dict[str, object]]:
    product = client.post(
        "/api/v1/products",
        json={"product_code": code, "product_name": f"产品 {code}"},
    ).json()
    version = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={
            "version_no": version_no,
            "owner_id": owner_id,
            "reviewer_id": reviewer_id,
        },
    ).json()
    return product, version


def create_ots(client: TestClient, name: str, version: str, website: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/ots-components",
        json={
            "ots_name": name,
            "ots_version": version,
            "official_website": website,
            "is_eol": False,
        },
    )
    assert response.status_code == 201
    return response.json()


def attach_ots(client: TestClient, version_id: int, ots_id: int) -> dict[str, object]:
    response = client.post(
        f"/api/v1/product-versions/{version_id}/ots",
        json={"ots_component_id": ots_id},
    )
    assert response.status_code == 201
    return response.json()


def add_batch(
    client: TestClient,
    *,
    batch_no: str,
    created_at: datetime,
    scope_snapshot: list[dict[str, object]],
    coverage: list[dict[str, object]],
) -> None:
    with client.app.state.database.session_factory.begin() as session:
        session.add(
            ImportBatch(
                batch_no=batch_no,
                format_version="1.0",
                package_file_name=f"{batch_no}.zip",
                package_sha256=hashlib.sha256(batch_no.encode()).hexdigest(),
                status="succeeded",
                manifest_json={
                    "scope_export_id": f"scope-{batch_no}",
                    "scope_file_sha256": "0" * 64,
                    "scope_snapshot": scope_snapshot,
                },
                scope_coverage_json=coverage,
                imported_by=1,
                started_at=created_at - timedelta(minutes=1),
                finished_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )


def setup_scope(client: TestClient) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    login(client)
    owner = create_user(client, "owner", ["product_owner"])
    reviewer = create_user(client, "reviewer", ["reviewer"])
    product_a, version_a = create_product_version(
        client,
        code="P-A",
        version_no="1.0",
        owner_id=owner["id"],
        reviewer_id=reviewer["id"],
    )
    _, version_b = create_product_version(
        client,
        code="P-B",
        version_no="2.0",
        owner_id=owner["id"],
        reviewer_id=reviewer["id"],
    )
    return owner, product_a, version_a, version_b


def test_scope_requires_admin_and_returns_empty_header_only_csv(client: TestClient) -> None:
    assert client.get("/api/v1/collector-scope").status_code == 401
    assert client.get("/api/v1/collector-scope/export").status_code == 401

    login(client)
    owner = create_user(client, "limited-owner", ["product_owner"])
    login(client, str(owner["login_name"]), "user-password")
    forbidden = client.get("/api/v1/collector-scope")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"

    login(client)
    preview = client.get("/api/v1/collector-scope")
    exported = client.get("/api/v1/collector-scope/export")
    assert preview.status_code == 200
    assert preview.json() == {
        "scope_count": 0,
        "items": [],
        "comparison_baseline": {"available": False, "batch_no": None, "finished_at": None},
        "changes": {"added_ots_ids": [], "removed_ots_ids": [], "added_count": 0, "removed_count": 0},
    }
    assert exported.status_code == 200
    assert exported.content == b"scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time\r\n"
    assert exported.headers["content-disposition"] == 'attachment; filename="collector_scope.csv"'
    UUID(exported.headers["x-scope-export-id"], version=4)
    assert exported.headers["x-content-sha256"] == hashlib.sha256(exported.content).hexdigest()


def test_scope_filters_inactive_relations_deduplicates_and_stays_read_only(client: TestClient) -> None:
    _, product_a, version_a, version_b = setup_scope(client)
    shared = create_ots(client, "Open,SSL", "3.0", "https://openssl.org/docs?x=1,2")
    excluded = create_ots(client, "disabled", "1.0", "https://disabled.test")
    attach_ots(client, int(version_a["id"]), int(shared["id"]))
    attach_ots(client, int(version_b["id"]), int(shared["id"]))
    disabled_relation = attach_ots(client, int(version_a["id"]), int(excluded["id"]))
    disabled = client.post(
        f"/api/v1/products/{product_a['id']}/versions/{version_a['id']}/disable",
        json={"row_version": version_a["row_version"]},
    )
    assert disabled.status_code == 200
    # The shared OTS remains active through version_b, while excluded only had the disabled version.

    with client.app.state.database.session_factory() as session:
        before = {
            "audit": session.scalar(select(func.count()).select_from(AuditLog)),
            "ots": session.scalar(select(func.count()).select_from(OtsComponent)),
            "relations": session.scalar(select(func.count()).select_from(ProductOts)),
            "batches": session.scalar(select(func.count()).select_from(ImportBatch)),
        }

    preview = client.get("/api/v1/collector-scope")
    exported = client.get("/api/v1/collector-scope/export")

    assert preview.status_code == 200
    payload = preview.json()
    assert payload["scope_count"] == 1
    assert [item["ots_id"] for item in payload["items"]] == [shared["id"]]
    assert set(payload["items"][0]) == {
        "ots_id", "ots_name", "ots_version", "official_website", "last_covered_time", "is_initial_collection"
    }
    assert payload["items"][0]["is_initial_collection"] is True
    assert "product_name" not in exported.text
    rows = list(csv.DictReader(StringIO(exported.content.decode("utf-8"), newline="")))
    assert len(rows) == 1
    assert rows[0]["ots_name"] == "Open,SSL"
    assert rows[0]["official_website"] == "https://openssl.org/docs?x=1,2"
    assert rows[0]["last_covered_time"] == ""
    assert int(rows[0]["ots_id"]) == shared["id"]

    with client.app.state.database.session_factory() as session:
        after = {
            "audit": session.scalar(select(func.count()).select_from(AuditLog)),
            "ots": session.scalar(select(func.count()).select_from(OtsComponent)),
            "relations": session.scalar(select(func.count()).select_from(ProductOts)),
            "batches": session.scalar(select(func.count()).select_from(ImportBatch)),
        }
        assert session.get(ProductOts, disabled_relation["id"]) is not None
    assert after == before


def test_scope_uses_latest_success_per_ots_and_reports_snapshot_changes(client: TestClient) -> None:
    _, _, version_a, _ = setup_scope(client)
    ots_a = create_ots(client, "OpenSSL", "3.0", "https://openssl.org")
    ots_b = create_ots(client, "zlib", "1.3", "https://zlib.net")
    attach_ots(client, int(version_a["id"]), int(ots_a["id"]))
    attach_ots(client, int(version_a["id"]), int(ots_b["id"]))
    old_time = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    new_time = datetime(2026, 8, 2, 9, 30, tzinfo=UTC)
    add_batch(
        client,
        batch_no="B-OLD",
        created_at=old_time,
        scope_snapshot=[{"ots_id": ots_a["id"]}, {"ots_id": 999}],
        coverage=[
            {"ots_id": ots_a["id"], "status": "succeeded", "covered_to": "2026-08-01T08:00:00.000Z"},
            {"ots_id": ots_b["id"], "status": "succeeded", "covered_to": "2026-08-01T07:00:00.000Z"},
        ],
    )
    add_batch(
        client,
        batch_no="B-NEW",
        created_at=new_time,
        scope_snapshot=[{"ots_id": ots_a["id"]}, {"ots_id": 999}],
        coverage=[
            {"ots_id": ots_a["id"], "status": "failed", "error": "timeout"},
            {"ots_id": ots_b["id"], "status": "succeeded", "covered_to": "2026-08-02T09:30:00.000Z"},
        ],
    )

    payload = client.get("/api/v1/collector-scope").json()
    items = {item["ots_id"]: item for item in payload["items"]}
    assert items[ots_a["id"]]["last_covered_time"] == "2026-08-01T08:00:00.000Z"
    assert items[ots_b["id"]]["last_covered_time"] == "2026-08-02T09:30:00.000Z"
    assert all(item["is_initial_collection"] is False for item in items.values())
    assert payload["comparison_baseline"] == {
        "available": True,
        "batch_no": "B-NEW",
        "finished_at": "2026-08-02T09:30:00Z",
    }
    assert payload["changes"] == {
        "added_ots_ids": [ots_b["id"]],
        "removed_ots_ids": [999],
        "added_count": 1,
        "removed_count": 1,
    }


def test_scope_csv_is_canonical_sorted_unique_and_hashes_exact_bytes(client: TestClient) -> None:
    _, _, version_a, _ = setup_scope(client)
    high = create_ots(client, "zlib", "1.3", "https://zlib.net")
    low = create_ots(client, "OpenSSL", "3.0", "https://openssl.org")
    attach_ots(client, int(version_a["id"]), int(high["id"]))
    attach_ots(client, int(version_a["id"]), int(low["id"]))

    first = client.get("/api/v1/collector-scope/export")
    second = client.get("/api/v1/collector-scope/export")
    first_id = first.headers["x-scope-export-id"]
    second_id = second.headers["x-scope-export-id"]
    assert first_id != second_id
    assert first.content.startswith(b"scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time\r\n")
    assert b"\n" not in first.content.replace(b"\r\n", b"")
    assert not first.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(StringIO(first.content.decode("utf-8"), newline="")))
    assert [int(row["ots_id"]) for row in rows] == sorted([int(low["id"]), int(high["id"])])
    assert {row["scope_export_id"] for row in rows} == {first_id}
    assert first.headers["x-content-sha256"] == hashlib.sha256(first.content).hexdigest()
    assert second.headers["x-content-sha256"] == hashlib.sha256(second.content).hexdigest()
    assert first.content.replace(first_id.encode(), b"<id>") == second.content.replace(second_id.encode(), b"<id>")


def test_invalid_success_history_returns_stable_error_without_partial_csv(client: TestClient) -> None:
    _, _, version_a, _ = setup_scope(client)
    ots = create_ots(client, "OpenSSL", "3.0", "https://openssl.org")
    attach_ots(client, int(version_a["id"]), int(ots["id"]))
    add_batch(
        client,
        batch_no="B-BAD",
        created_at=datetime(2026, 8, 3, tzinfo=UTC),
        scope_snapshot=[{"ots_id": ots["id"]}],
        coverage=[{"ots_id": ots["id"], "status": "succeeded", "covered_to": "not-a-date"}],
    )

    preview = client.get("/api/v1/collector-scope")
    exported = client.get("/api/v1/collector-scope/export")
    assert preview.status_code == 500
    assert preview.json()["code"] == "COLLECTOR_SCOPE_HISTORY_INVALID"
    assert "not-a-date" not in preview.text
    assert exported.status_code == 500
    assert exported.headers["content-type"].startswith("application/json")
    assert "x-content-sha256" not in exported.headers

