from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.main import create_app
from app.infrastructure.settings import Settings
from app.migrations import apply_migrations
from app.models.imports import ImportBatch
from app.models.ots import OtsComponent
from app.models.user import AuditLog, Base
from app.services.authentication import AuthenticationService
from tests.package_fixtures import (
    base_rows,
    build_package,
    build_zip_with_member,
    build_zip_with_symlink,
)
from uuid import uuid4


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    database_path = tmp_path / "import-packages.db"
    temp_path = tmp_path / "incoming"
    archive_path = tmp_path / "archive"
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(temp_path))
    monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(archive_path))
    application = create_app()
    Base.metadata.create_all(application.state.database.engine)
    AuthenticationService(application.state.database.session_factory).initialize_admin(
        "admin", "初始管理员", "admin-password"
    )
    with application.state.database.session_factory.begin() as session:
        session.add(
            OtsComponent(
                ots_name="OpenSSL",
                ots_version="3.0.0",
                official_website="https://openssl.org",
                is_eol=False,
            )
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


def package_upload(package: bytes, file_name: str = "ots_intelligence_20260822_010203.zip") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (file_name, package, "application/zip")}


def test_admin_uploads_valid_package_and_reads_preview_without_business_audit(client: TestClient) -> None:
    login(client)
    response = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package()),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "validated"
    assert payload["batch_no"] == "BATCH-20260822-001"
    assert payload["scope_count"] == 1
    assert payload["classification_basis"] == "package_structure_v1"
    assert payload["final_import_diff"] is False
    assert payload["can_import"] is False
    assert "archive_path" not in payload

    detail = client.get(f"/api/v1/import-packages/{payload['id']}")
    assert detail.status_code == 200
    assert detail.json() == payload

    application = client.app
    with application.state.database.session_factory() as session:
        batch = session.get(ImportBatch, payload["id"])
        assert batch is not None
        assert batch.status == "validated"
        assert batch.archive_path is not None
        assert (application.state.settings.import_archive_dir / batch.archive_path).is_file()
        assert session.scalar(select(func.count(AuditLog.id))) == 0
    assert list(application.state.settings.import_temp_dir.glob("*")) == []


def test_duplicate_package_returns_existing_batch_without_second_row(client: TestClient) -> None:
    login(client)
    package = build_package()
    first = client.post("/api/v1/import-packages/validate", files=package_upload(package))
    second = client.post("/api/v1/import-packages/validate", files=package_upload(package))

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["duplicate"] is True
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(ImportBatch.id))) == 1


def test_duplicate_batch_number_with_different_package_returns_existing_batch(client: TestClient) -> None:
    login(client)
    first = client.post("/api/v1/import-packages/validate", files=package_upload(build_package()))
    rows = base_rows()
    rows["vulnerabilities.csv"][0]["description"] = "内容不同但批次号相同"
    second = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package(rows=rows)),
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["duplicate"] is True
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(ImportBatch.id))) == 1


def test_failed_validation_persists_bounded_errors_and_downloads_csv(client: TestClient) -> None:
    login(client)
    rows = base_rows()
    rows["matches.csv"][0]["ots_id"] = 999
    response = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package(rows=rows)),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["errors"][0]["file_name"] == "matches.csv"
    assert payload["errors"][0]["row_number"] == 2
    assert payload["errors"][0]["field"] == "ots_id"
    assert payload["total_error_count"] >= 1

    download = client.get(f"/api/v1/import-packages/{payload['id']}/errors")
    assert download.status_code == 200
    assert download.headers["content-disposition"] == 'attachment; filename="package_validation_errors.csv"'
    assert download.content.startswith(
        b"error_code,file_name,row_number,field,reason,rejected_value\r\n"
    )
    with client.app.state.database.session_factory() as session:
        batch = session.get(ImportBatch, payload["id"])
        assert batch is not None
        assert batch.status == "failed"
        assert batch.archive_path is None
        assert session.scalar(select(func.count(AuditLog.id))) == 0
    assert list(client.app.state.settings.import_temp_dir.glob("*")) == []


def test_unsafe_zip_still_leaves_identifiable_failed_batch_and_no_temp_file(client: TestClient) -> None:
    login(client)
    response = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(b"not-a-zip"),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["batch_no"].startswith("upload:")
    assert payload["errors"][0]["error_code"] == "PACKAGE_STRUCTURE_INVALID"
    assert list(client.app.state.settings.import_temp_dir.glob("*")) == []


@pytest.mark.parametrize(
    ("package", "expected_code"),
    [
        (build_zip_with_member("../manifest.csv"), "PACKAGE_ZIP_UNSAFE"),
        (build_zip_with_symlink(), "PACKAGE_ZIP_UNSAFE"),
        (build_package(override_files={"cwes.csv": b"x" * 1_000_000}), "PACKAGE_TOO_LARGE"),
    ],
)
def test_malicious_zip_is_rejected_vertically_without_temp_residue(
    client: TestClient,
    package: bytes,
    expected_code: str,
) -> None:
    login(client)
    response = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(package),
    )

    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["errors"][0]["error_code"] == expected_code
    assert list(client.app.state.settings.import_temp_dir.glob("*")) == []


def test_unexpected_validator_failure_marks_batch_failed_and_cleans_temp(client: TestClient, monkeypatch) -> None:
    login(client)

    def fail_validation(*_args, **_kwargs):
        raise RuntimeError("injected validator failure")

    monkeypatch.setattr("app.services.import_packages.validate_package", fail_validation)
    response = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package()),
    )

    assert response.status_code == 500
    with client.app.state.database.session_factory() as session:
        batches = list(session.scalars(select(ImportBatch)).all())
        assert len(batches) == 1
        assert batches[0].status == "failed"
        assert batches[0].error_json["items"][0]["error_code"] == "INTERNAL_ERROR"
    assert list(client.app.state.settings.import_temp_dir.glob("*")) == []


def test_validated_batch_has_no_error_download(client: TestClient) -> None:
    login(client)
    uploaded = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package()),
    ).json()

    response = client.get(f"/api/v1/import-packages/{uploaded['id']}/errors")
    assert response.status_code == 409
    assert response.json()["code"] == "PACKAGE_ERRORS_NOT_AVAILABLE"


def test_package_routes_require_authentication_and_admin_role(client: TestClient) -> None:
    unauthenticated = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package()),
    )
    assert unauthenticated.status_code == 401

    login(client)
    created = client.post(
        "/api/v1/users",
        json={
            "login_name": "owner",
            "display_name": "产品负责人",
            "password": "owner-password",
            "roles": ["product_owner"],
        },
    )
    assert created.status_code == 201
    client.cookies.clear()
    login(client, "owner", "owner-password")
    forbidden = client.post(
        "/api/v1/import-packages/validate",
        files=package_upload(build_package()),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "AUTH_FORBIDDEN"


def test_package_detail_not_found_is_stable(client: TestClient) -> None:
    login(client)
    response = client.get("/api/v1/import-packages/9999")
    assert response.status_code == 404
    assert response.json()["code"] == "PACKAGE_BATCH_NOT_FOUND"


def test_mysql_validates_package_with_existing_schema_and_json_fields(tmp_path: Path, monkeypatch) -> None:
    configured_url = Settings.from_environment().database_url
    assert configured_url is not None
    url = make_url(configured_url)
    database_name = f"ots07_test_{uuid4().hex}"
    admin_engine = create_engine(url.set(database="mysql"))
    test_engine = None
    application = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"))
        test_url = url.set(database=database_name)
        test_engine = create_engine(test_url)
        apply_migrations(test_engine, Path(__file__).parents[1] / "migrations")
        tables_before = set(inspect(test_engine).get_table_names())
        assert "import_batch" in tables_before

        monkeypatch.setenv("OTS_DATABASE_URL", test_url.render_as_string(hide_password=False))
        monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(tmp_path / "mysql-incoming"))
        monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(tmp_path / "mysql-archive"))
        application = create_app()
        AuthenticationService(application.state.database.session_factory).initialize_admin(
            "admin", "初始管理员", "admin-password"
        )
        with application.state.database.session_factory.begin() as session:
            session.add(OtsComponent(ots_name="OpenSSL", ots_version="3.0.0", official_website="https://openssl.org", is_eol=False))

        with TestClient(application, raise_server_exceptions=False) as mysql_client:
            login(mysql_client)
            response = mysql_client.post(
                "/api/v1/import-packages/validate",
                files=package_upload(build_package()),
            )
            assert response.status_code == 201
            assert response.json()["status"] == "validated"
            with application.state.database.session_factory() as session:
                batch = session.get(ImportBatch, response.json()["id"])
                assert isinstance(batch.manifest_json, dict)
                assert isinstance(batch.result_json, dict)
                assert isinstance(batch.scope_coverage_json, list)
                assert session.scalar(select(func.count(AuditLog.id))) == 0
        assert set(inspect(test_engine).get_table_names()) == tables_before
    finally:
        if application is not None:
            application.state.database.engine.dispose()
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
