from __future__ import annotations

from collections.abc import Iterator
import hashlib
from pathlib import Path
import time
import tracemalloc
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url

from app.infrastructure.settings import Settings
from app.main import create_app
from app.migrations import apply_migrations
from app.models.imports import ImportBatch, Vulnerability
from app.models.user import AuditLog, Base
from app.services.authentication import AuthenticationService
from tests.package_fixtures import base_rows, build_package, nvd_row


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{tmp_path / 'packages.db'}")
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


def login(client: TestClient, login_name: str = "admin", password: str = "admin-password") -> None:
    assert client.post("/api/v1/auth/login", json={"login_name": login_name, "password": password}).status_code == 200


def upload(package: bytes, name: str = "ots_intelligence_20260822_010203.zip"):
    return {"file": (name, package, "application/zip")}


def validate(client: TestClient, package: bytes | None = None):
    return client.post("/api/v1/import-packages/validate", files=upload(package or build_package()))


def test_admin_previews_real_database_diff_then_confirms_transaction(client: TestClient) -> None:
    login(client)
    preview = validate(client)
    assert preview.status_code == 201
    payload = preview.json()
    assert payload["status"] == "validated"
    assert payload["source_name"] == "nvd"
    assert payload["source_release"] == "fkie-cad/nvd-json-data-feeds@2026-08-22"
    assert payload["summary"] == {"total": 1, "new": 1, "update": 0, "duplicate": 0, "conflict": 0, "error": 0}
    assert payload["can_import"] is True
    assert payload["final_import_diff"] is False

    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(Vulnerability.id))) == 0
        assert session.scalar(select(func.count(AuditLog.id))) == 0

    confirmed = client.post(f"/api/v1/import-packages/{payload['id']}/confirm")
    assert confirmed.status_code == 200
    result = confirmed.json()
    assert result["status"] == "succeeded"
    assert result["final_import_diff"] is True
    assert result["can_import"] is False
    assert result["summary"]["new"] == 1
    assert result["internal_matching_pending"] is True

    with client.app.state.database.session_factory() as session:
        vulnerability = session.scalar(select(Vulnerability))
        assert vulnerability is not None
        assert vulnerability.cve_id == "CVE-2026-0001"
        assert vulnerability.source_identifier == "security@example.test"
        assert len(vulnerability.cvss_json) == 1
        assert vulnerability.cvss31_score == 7.5
        assert vulnerability.configurations_json[0]["nodes"]
        assert vulnerability.affected_ranges_json[0]["product"] == "openssl"
        audit = session.scalar(select(AuditLog))
        assert audit is not None
        assert audit.action == "batch_upsert"
        assert audit.object_type == "vulnerability"
        assert audit.detail_json["new"] == 1


def test_same_package_and_repeated_confirmation_are_idempotent(client: TestClient) -> None:
    login(client)
    package = build_package()
    first = validate(client, package)
    duplicate = validate(client, package)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == first.json()["id"]
    assert duplicate.json()["duplicate"] is True

    first_confirm = client.post(f"/api/v1/import-packages/{first.json()['id']}/confirm")
    second_confirm = client.post(f"/api/v1/import-packages/{first.json()['id']}/confirm")
    assert first_confirm.status_code == 200
    assert second_confirm.status_code == 200
    assert second_confirm.json()["duplicate"] is True
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(Vulnerability.id))) == 1
        assert session.scalar(select(func.count(AuditLog.id))) == 1


def test_same_batch_number_with_different_sha_returns_explicit_conflict(client: TestClient) -> None:
    login(client)
    assert validate(client).status_code == 201
    rows = base_rows()
    rows["nvd_cves.csv"][0]["description"] = "同批次不同内容"
    conflict = validate(client, build_package(rows=rows))
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "PACKAGE_BATCH_CONFLICT"
    assert conflict.json()["existing_sha256_prefix"] != conflict.json()["incoming_sha256_prefix"]
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(ImportBatch.id))) == 1


def test_failed_validation_has_precise_download_and_cannot_confirm(client: TestClient) -> None:
    login(client)
    rows = base_rows()
    rows["nvd_cves.csv"][0]["cvss_json"] = "{"
    failed = validate(client, build_package(rows=rows))
    assert failed.status_code == 201
    payload = failed.json()
    assert payload["status"] == "failed"
    assert payload["errors"][0]["row_number"] == 2
    assert payload["errors"][0]["field"] == "cvss_json"
    download = client.get(f"/api/v1/import-packages/{payload['id']}/errors")
    assert download.status_code == 200
    assert b"PACKAGE_CSV_INVALID" in download.content
    confirm = client.post(f"/api/v1/import-packages/{payload['id']}/confirm")
    assert confirm.status_code == 409
    assert confirm.json()["code"] == "PACKAGE_BATCH_NOT_VALIDATED"


def test_preview_drift_becomes_conflict_and_does_not_overwrite(client: TestClient) -> None:
    login(client)
    preview = validate(client).json()
    with client.app.state.database.session_factory.begin() as session:
        session.add(
            Vulnerability(
                cve_id="CVE-2026-0001",
                source_identifier="other",
                source_status="Analyzed",
                description="并发写入",
                published_at=None,
                source_modified_at=None,
                cwe_json=[],
                affected_ranges_json=[],
                references_json=[],
                cvss_json=[],
                configurations_json=[],
                is_kev=False,
                import_batch_id=preview["id"],
                content_sha256="f" * 64,
            )
        )
    response = client.post(f"/api/v1/import-packages/{preview['id']}/confirm")
    assert response.status_code == 409
    assert response.json()["code"] == "PACKAGE_IMPORT_CONFLICT"
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(Vulnerability.description)) == "并发写入"
        assert session.scalar(select(func.count(AuditLog.id))) == 0


def test_injected_write_failure_rolls_back_facts_and_audit_and_marks_failed(client: TestClient, monkeypatch) -> None:
    login(client)
    preview = validate(client).json()

    def fail(*_args, **_kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(client.app.state.import_package_service, "_apply_records", fail)
    response = client.post(f"/api/v1/import-packages/{preview['id']}/confirm")
    assert response.status_code == 500
    with client.app.state.database.session_factory() as session:
        assert session.get(ImportBatch, preview["id"]).status == "failed"
        assert session.scalar(select(func.count(Vulnerability.id))) == 0
        assert session.scalar(select(func.count(AuditLog.id))) == 0


def test_rejected_update_preserves_manual_and_future_enrichment_fields(client: TestClient) -> None:
    login(client)
    first = validate(client).json()
    assert client.post(f"/api/v1/import-packages/{first['id']}/confirm").status_code == 200
    with client.app.state.database.session_factory.begin() as session:
        vulnerability = session.scalar(select(Vulnerability))
        vulnerability.ai_analysis_suggestion = "人工建议"
        vulnerability.is_kev = True

    rows = base_rows()
    rows["nvd_cves.csv"][0]["vuln_status"] = "Rejected"
    rows["nvd_cves.csv"][0]["last_modified_at"] = "2026-08-03T00:00:00Z"
    rows["nvd_cves.csv"][0]["affected_software_json"] = "[]"
    rows["nvd_cves.csv"][0]["configurations_json"] = "[]"
    second = validate(client, build_package(rows=rows, batch_no="BATCH-20260822-002")).json()
    assert second["summary"]["update"] == 1
    assert client.post(f"/api/v1/import-packages/{second['id']}/confirm").status_code == 200
    with client.app.state.database.session_factory() as session:
        vulnerability = session.scalar(select(Vulnerability))
        assert vulnerability.source_status == "Rejected"
        assert vulnerability.ai_analysis_suggestion == "人工建议"
        assert vulnerability.is_kev is True


def test_routes_require_admin_for_validate_detail_confirm_and_errors(client: TestClient) -> None:
    assert validate(client).status_code == 401
    login(client)
    assert client.post(
        "/api/v1/users",
        json={"login_name": "owner", "display_name": "负责人", "password": "owner-password", "roles": ["product_owner"]},
    ).status_code == 201
    batch = validate(client).json()
    client.cookies.clear()
    login(client, "owner", "owner-password")
    assert validate(client).status_code == 403
    assert client.get(f"/api/v1/import-packages/{batch['id']}").status_code == 403
    assert client.post(f"/api/v1/import-packages/{batch['id']}/confirm").status_code == 403


def test_ten_thousand_cves_preview_and_confirm_under_five_minutes(client: TestClient) -> None:
    login(client)
    rows = base_rows()
    rows["nvd_cves.csv"] = [
        {
            **nvd_row(f"CVE-2026-{index + 1:04d}"),
            "description": hashlib.sha256(str(index).encode()).hexdigest() * 2,
        }
        for index in range(10_000)
    ]
    package = build_package(rows=rows, batch_no="NVD-10000-PERFORMANCE")
    tracemalloc.start()
    started = time.perf_counter()
    try:
        preview = validate(client, package)
        assert preview.status_code == 201
        confirmed = client.post(f"/api/v1/import-packages/{preview.json()['id']}/confirm")
        duration = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert confirmed.status_code == 200
    assert confirmed.json()["summary"]["new"] == 10_000
    print(f"OTS-07 10,000 CVE preview+confirm: {duration:.2f}s, peak {peak / 1024 / 1024:.2f} MiB")
    assert duration < 300
    assert peak < 256 * 1024 * 1024
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(Vulnerability.id))) == 10_000


def test_mysql_migration_and_confirm_import(tmp_path: Path, monkeypatch) -> None:
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
        assert "vulnerability" in inspect(test_engine).get_table_names()
        columns = {item["name"] for item in inspect(test_engine).get_columns("vulnerability")}
        assert {"source_identifier", "cvss_json", "affected_ranges_json", "configurations_json"} <= columns

        monkeypatch.setenv("OTS_DATABASE_URL", test_url.render_as_string(hide_password=False))
        monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(tmp_path / "mysql-incoming"))
        monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(tmp_path / "mysql-archive"))
        application = create_app()
        AuthenticationService(application.state.database.session_factory).initialize_admin("admin", "管理员", "admin-password")
        with TestClient(application, raise_server_exceptions=False) as mysql_client:
            login(mysql_client)
            preview = validate(mysql_client).json()
            confirmed = mysql_client.post(f"/api/v1/import-packages/{preview['id']}/confirm")
            assert confirmed.status_code == 200
            with application.state.database.session_factory() as session:
                assert session.scalar(select(func.count(Vulnerability.id))) == 1
                assert session.scalar(select(func.count(AuditLog.id))) == 1
    finally:
        if application is not None:
            application.state.database.engine.dispose()
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
