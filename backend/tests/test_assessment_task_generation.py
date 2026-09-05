from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.engine import make_url

from app.main import create_app
from app.infrastructure.settings import Settings
from app.migrations import apply_migrations
from app.models.assessments import ProductAssessment
from app.models.imports import ImportBatch, Vulnerability
from app.models.user import AuditLog, Base
from app.services.authentication import AuthenticationService
from app.services.assessment_basis_initialization import AssessmentBasisInitializer
from app.services.assessment_tasks import AssessmentTaskService, TaskOperation, TaskPlan
from app.services.automatic_reassessment import AssessmentBasis
from tests.package_fixtures import base_rows, build_package


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{tmp_path / 'assessment-tasks.db'}")
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


def login(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "admin-password"},
    ).status_code == 200


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


def create_product_ots(
    client: TestClient,
    *,
    code: str,
    owner_id: int,
    reviewer_id: int,
    ots_component_id: int,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    product = client.post(
        "/api/v1/products", json={"product_code": code, "product_name": f"产品 {code}"}
    ).json()
    version = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={
            "version_no": "1.0",
            "owner_id": owner_id,
            "reviewer_id": reviewer_id,
        },
    ).json()
    relation_response = client.post(
        f"/api/v1/product-versions/{version['id']}/ots",
        json={"ots_component_id": ots_component_id},
    )
    assert relation_response.status_code == 201
    return product, version, relation_response.json()


def import_batch(client: TestClient) -> int:
    validated = client.post(
        "/api/v1/import-packages/validate",
        files={
            "file": (
                "ots_intelligence_20260822_010203.zip",
                build_package(),
                "application/zip",
            )
        },
    ).json()
    assert client.post(f"/api/v1/import-packages/{validated['id']}/confirm").status_code == 200
    return validated["id"]


def import_package(client: TestClient, package: bytes, file_name: str) -> int:
    validated = client.post(
        "/api/v1/import-packages/validate",
        files={"file": (file_name, package, "application/zip")},
    ).json()
    response = client.post(f"/api/v1/import-packages/{validated['id']}/confirm")
    assert response.status_code == 200
    return validated["id"]


def setup_scope(client: TestClient, *, product_count: int = 1) -> dict[str, object]:
    login(client)
    owners = [create_user(client, f"owner-{index}", ["product_owner"]) for index in range(product_count)]
    reviewer = create_user(client, "reviewer", ["reviewer"])
    ots = client.post(
        "/api/v1/ots-components",
        json={
            "ots_name": "OpenSSL",
            "ots_version": "3.0.0",
            "official_website": "https://openssl.org",
            "is_eol": False,
        },
    ).json()
    scopes = [
        create_product_ots(
            client,
            code=f"P-{index}",
            owner_id=owners[index]["id"],
            reviewer_id=reviewer["id"],
            ots_component_id=ots["id"],
        )
        for index in range(product_count)
    ]
    return {
        "owners": owners,
        "reviewer": reviewer,
        "ots": ots,
        "scopes": scopes,
        "batch_id": import_batch(client),
    }


def assessment_rows(client: TestClient) -> list[dict[str, object]]:
    with client.app.state.database.engine.connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM product_assessment ORDER BY product_ots_id, revision_no")
            ).mappings()
        ]
    for row in rows:
        for field in ("assessment_basis_json", "reassess_changes_json"):
            if isinstance(row.get(field), str):
                row[field] = json.loads(row[field])
    return rows


def test_preview_expands_one_candidate_to_each_active_product_without_writes(
    client: TestClient,
) -> None:
    scope = setup_scope(client, product_count=2)

    preview = client.get(
        f"/api/v1/import-packages/{scope['batch_id']}/ots-match-preview"
    )

    assert preview.status_code == 200
    tasks = preview.json()["task_generation"]
    assert tasks["status"] == "pending"
    assert tasks["task_inserted_count"] == 2
    assert tasks["task_reassess_count"] == 0
    assert tasks["task_failed_count"] == 0
    assert [sample["owner_id"] for sample in tasks["task_samples"]] == [
        owner["id"] for owner in scope["owners"]
    ]
    with client.app.state.database.engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM product_assessment")) == 0


def test_execute_recalculates_product_relations_changed_after_preview(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    preview = client.get(
        f"/api/v1/import-packages/{scope['batch_id']}/ots-match-preview"
    ).json()
    assert preview["task_generation"]["task_inserted_count"] == 1
    extra_owner = create_user(client, "late-owner", ["product_owner"])
    create_product_ots(
        client,
        code="P-LATE",
        owner_id=extra_owner["id"],
        reviewer_id=scope["reviewer"]["id"],
        ots_component_id=scope["ots"]["id"],
    )

    executed = client.post(
        f"/api/v1/import-packages/{scope['batch_id']}/ots-matches"
    ).json()

    assert executed["task_generation"]["task_inserted_count"] == 2
    assert {row["owner_id"] for row in assessment_rows(client)} == {
        scope["owners"][0]["id"],
        extra_owner["id"],
    }


def test_execute_creates_independent_pending_tasks_and_is_idempotent(
    client: TestClient,
) -> None:
    scope = setup_scope(client, product_count=2)

    first = client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    repeated = client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")

    assert first.status_code == 200
    assert first.json()["task_generation"]["task_inserted_count"] == 2
    assert repeated.status_code == 200
    assert repeated.json()["task_generation"]["task_inserted_count"] == 0
    assert repeated.json()["task_generation"]["task_unchanged_count"] == 2
    rows = assessment_rows(client)
    assert len(rows) == 2
    assert {row["status"] for row in rows} == {"pending"}
    assert {row["applicability"] for row in rows} == {"pending"}
    assert {row["revision_no"] for row in rows} == {1}
    assert {row["is_current"] for row in rows} == {1}
    assert {row["owner_id"] for row in rows} == {
        owner["id"] for owner in scope["owners"]
    }
    assert all(row["analysis_summary"] is None for row in rows)
    assert all(row["assessment_basis_sha256"] for row in rows)
    assert all(row["assessment_basis_json"]["schema_version"] == "1.0" for row in rows)


def test_candidate_execution_is_blocked_until_current_bases_are_initialized(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text(
            "UPDATE product_assessment SET assessment_basis_sha256=NULL, assessment_basis_json=NULL"
        ))

    blocked = client.post(
        f"/api/v1/import-packages/{scope['batch_id']}/ots-matches"
    )

    assert blocked.status_code == 500
    assert blocked.json()["code"] == "MATCH_EXECUTION_FAILED"
    rows = assessment_rows(client)
    assert len(rows) == 1
    assert rows[0]["assessment_basis_sha256"] is None

    initializer = AssessmentBasisInitializer(client.app.state.database.session_factory)
    assert initializer.run(dry_run=False)["remaining_count"] == 0
    repeated = client.post(
        f"/api/v1/import-packages/{scope['batch_id']}/ots-matches"
    )

    assert repeated.status_code == 200
    assert repeated.json()["task_generation"]["task_unchanged_count"] == 1


def test_basis_initializer_dry_run_and_repeated_batches_are_safe(
    client: TestClient,
) -> None:
    scope = setup_scope(client, product_count=2)
    client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text(
            "UPDATE product_assessment SET status='completed', row_version=7, assessment_basis_sha256=NULL, assessment_basis_json=NULL"
        ))
    initializer = AssessmentBasisInitializer(client.app.state.database.session_factory)

    preview = initializer.run(dry_run=True, batch_size=1)
    untouched = assessment_rows(client)
    applied = initializer.run(dry_run=False, batch_size=1)
    repeated = initializer.run(dry_run=False, batch_size=1)
    rows = assessment_rows(client)

    assert preview == {
        "dry_run": True,
        "scanned_count": 2,
        "eligible_count": 2,
        "initialized_count": 0,
        "remaining_count": 2,
    }
    assert all(row["assessment_basis_sha256"] is None for row in untouched)
    assert applied["initialized_count"] == 2
    assert applied["remaining_count"] == 0
    assert repeated["initialized_count"] == 0
    assert {(row["status"], row["row_version"], row["revision_no"]) for row in rows} == {
        ("completed", 7, 1)
    }
    assert all(row["assessment_basis_sha256"] for row in rows)
    assert all(row["reassess_changes_json"] is None for row in rows)


def test_mysql_basis_initialization_recovers_after_committed_batch(
    monkeypatch, tmp_path: Path
) -> None:
    configured_url = Settings.from_environment().database_url
    assert configured_url is not None
    url = make_url(configured_url)
    database_name = f"ots16_init_{uuid4().hex}"
    admin_engine = create_engine(url.set(database="mysql"))
    test_engine = None
    application = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(
                text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4")
            )
        test_url = url.set(database=database_name)
        test_engine = create_engine(test_url)
        assert apply_migrations(
            test_engine, Path(__file__).parents[1] / "migrations"
        ) == list(range(1, 14))
        monkeypatch.setenv(
            "OTS_DATABASE_URL", test_url.render_as_string(hide_password=False)
        )
        monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(tmp_path / "mysql-incoming"))
        monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(tmp_path / "mysql-archive"))
        application = create_app()
        AuthenticationService(application.state.database.session_factory).initialize_admin(
            "admin", "初始管理员", "admin-password"
        )
        with TestClient(application, raise_server_exceptions=False) as mysql_client:
            scope = setup_scope(mysql_client, product_count=2)
            mysql_client.post(
                f"/api/v1/import-packages/{scope['batch_id']}/ots-matches"
            )
            with application.state.database.engine.begin() as connection:
                connection.execute(text(
                    "UPDATE product_assessment SET status='completed', row_version=7, "
                    "assessment_basis_sha256=NULL, assessment_basis_json=NULL"
                ))
            initializer = AssessmentBasisInitializer(
                application.state.database.session_factory
            )
            original_page = initializer._page
            page_calls = 0

            def interrupted_page(session, *, last_id: int, limit: int):
                nonlocal page_calls
                page_calls += 1
                if page_calls == 2:
                    raise RuntimeError("simulated interruption")
                return original_page(session, last_id=last_id, limit=limit)

            monkeypatch.setattr(initializer, "_page", interrupted_page)
            with pytest.raises(RuntimeError, match="simulated interruption"):
                initializer.run(dry_run=False, batch_size=1)
            with application.state.database.engine.connect() as connection:
                assert connection.scalar(text(
                    "SELECT COUNT(*) FROM product_assessment "
                    "WHERE assessment_basis_sha256 IS NOT NULL"
                )) == 1

            resumed = AssessmentBasisInitializer(
                application.state.database.session_factory
            ).run(dry_run=False, batch_size=1)
            repeated = AssessmentBasisInitializer(
                application.state.database.session_factory
            ).run(dry_run=False, batch_size=1)
            assert resumed["remaining_count"] == 0
            assert repeated["initialized_count"] == 0
            rows = assessment_rows(mysql_client)
            assert {(row["status"], row["row_version"]) for row in rows} == {
                ("completed", 7)
            }

            with application.state.database.session_factory.begin() as session:
                vulnerability = session.scalar(select(Vulnerability))
                assert vulnerability is not None
                vulnerability.source_status = "Rejected"
            rejected = mysql_client.post(
                f"/api/v1/import-packages/{scope['batch_id']}/ots-matches"
            )
            assert rejected.status_code == 200
            assert rejected.json()["task_generation"]["task_reassess_count"] == 2
            revisions = assessment_rows(mysql_client)
            assert [row["revision_no"] for row in revisions] == [1, 2, 1, 2]
            assert len([row for row in revisions if row["is_current"]]) == 2
            assert {row["owner_id"] for row in revisions if row["is_current"]} == {
                owner["id"] for owner in scope["owners"]
            }

            with application.state.database.engine.begin() as connection:
                connection.execute(text(
                    "UPDATE product_assessment SET status='completed' "
                    "WHERE is_current=1"
                ))
            with application.state.database.session_factory.begin() as session:
                vulnerability = session.scalar(select(Vulnerability))
                assert vulnerability is not None
                vulnerability.source_status = "Analyzed"
                vulnerability.cvss31_score = 8.8
                vulnerability.cvss31_vector = (
                    "CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H"
                )
                ranges = [dict(item) for item in vulnerability.affected_ranges_json]
                ranges[0]["versionEndExcluding"] = "3.0.9"
                vulnerability.affected_ranges_json = ranges
            source_matrix = mysql_client.post(
                f"/api/v1/import-packages/{scope['batch_id']}/ots-matches"
            )
            assert source_matrix.status_code == 200
            assert source_matrix.json()["task_generation"]["task_reassess_count"] == 2
            revisions = assessment_rows(mysql_client)
            assert [row["revision_no"] for row in revisions] == [1, 2, 3, 1, 2, 3]

            with application.state.database.engine.begin() as connection:
                connection.execute(text(
                    "UPDATE product_assessment SET status='completed' "
                    "WHERE is_current=1"
                ))
            first_relation = scope["scopes"][0][2]
            first_version = scope["scopes"][0][1]
            disabled = mysql_client.post(
                f"/api/v1/product-versions/{first_version['id']}/ots/"
                f"{first_relation['id']}/disable",
                json={"row_version": first_relation["row_version"]},
            )
            assert disabled.status_code == 200
            revisions = assessment_rows(mysql_client)
            first_product = [
                row for row in revisions
                if row["product_ots_id"] == first_relation["id"]
            ]
            assert [row["revision_no"] for row in first_product] == [1, 2, 3, 4]
            assert sum(bool(row["is_current"]) for row in first_product) == 1
            assert first_product[-1]["parent_revision_id"] == first_product[-2]["id"]
            assert "product_context" in first_product[-1]["reassess_changes_json"]["change_types"]
    finally:
        if application is not None:
            application.state.database.engine.dispose()
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()


def test_stale_task_plan_cannot_overwrite_newer_assessment_basis(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    factory = client.app.state.database.session_factory
    task_service = AssessmentTaskService()

    with factory() as stale_session:
        current = stale_session.scalar(select(ProductAssessment))
        assert current is not None
        context = task_service._repository.get_product_context(
            stale_session, current.product_ots_id
        )
        assert context is not None
        operation = TaskOperation(
            action="updated",
            vulnerability_id=current.vulnerability_id,
            cve_id="CVE-2026-1001",
            context=context,
            source_modified_at=current.based_on_source_modified_at,
            current=current,
            basis=AssessmentBasis({"schema_version": "1.0"}, "f" * 64),
            changes=None,
        )
        with factory.begin() as winning_session:
            winning_session.execute(
                update(ProductAssessment)
                .where(ProductAssessment.id == current.id)
                .values(row_version=ProductAssessment.row_version + 1)
            )

        with pytest.raises(RuntimeError, match="conflict"):
            task_service.apply(stale_session, TaskPlan((operation,), {}))

    rows = assessment_rows(client)
    assert rows[0]["row_version"] == 2
    assert rows[0]["assessment_basis_sha256"] != "f" * 64


def test_disabled_product_version_and_unavailable_owner_are_reported(
    client: TestClient,
) -> None:
    scope = setup_scope(client, product_count=4)
    product_disabled, _, _ = scope["scopes"][1]
    _, version_disabled, _ = scope["scopes"][2]
    unavailable_owner = scope["owners"][3]
    assert client.post(
        f"/api/v1/products/{product_disabled['id']}/disable", json={"row_version": 1}
    ).status_code == 200
    assert client.post(
        f"/api/v1/products/{scope['scopes'][2][0]['id']}/versions/{version_disabled['id']}/disable",
        json={"row_version": 1},
    ).status_code == 200
    assert client.post(
        f"/api/v1/users/{unavailable_owner['id']}/disable", json={"row_version": 1}
    ).status_code == 200

    tasks = client.get(
        f"/api/v1/import-packages/{scope['batch_id']}/ots-match-preview"
    ).json()["task_generation"]

    assert tasks["task_inserted_count"] == 1
    assert tasks["task_skipped_count"] == 3
    assert tasks["skip_reason_counts"] == {
        "OWNER_UNAVAILABLE": 1,
        "PRODUCT_DISABLED": 1,
        "PRODUCT_VERSION_DISABLED": 1,
    }


def test_candidate_without_product_relation_has_stable_skip_reason(client: TestClient) -> None:
    login(client)
    client.post(
        "/api/v1/ots-components",
        json={
            "ots_name": "OpenSSL", "ots_version": "3.0.0",
            "official_website": "https://openssl.org", "is_eol": False,
        },
    )
    batch_id = import_batch(client)

    tasks = client.get(
        f"/api/v1/import-packages/{batch_id}/ots-match-preview"
    ).json()["task_generation"]

    assert tasks["task_inserted_count"] == 0
    assert tasks["skip_reason_counts"] == {"NO_ACTIVE_PRODUCT_OTS": 1}


def test_empty_pending_task_follows_current_product_owner(client: TestClient) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    new_owner = create_user(client, "replacement-owner", ["product_owner"])
    product, version, _ = scope["scopes"][0]
    updated = client.put(
        f"/api/v1/products/{product['id']}/versions/{version['id']}",
        json={
            "version_no": version["version_no"],
            "description": version["description"],
            "owner_id": new_owner["id"],
            "reviewer_id": scope["reviewer"]["id"],
            "row_version": version["row_version"],
        },
    )
    assert updated.status_code == 200

    tasks = client.post(
        f"/api/v1/import-packages/{batch_id}/ots-matches"
    ).json()["task_generation"]

    assert tasks["task_updated_count"] == 1
    rows = assessment_rows(client)
    assert rows[0]["owner_id"] == new_owner["id"]
    assert rows[0]["row_version"] == 2


def test_completed_assessment_gets_one_reassess_revision_for_material_evidence_change(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    assert client.post(f"/api/v1/import-packages/{batch_id}/ots-matches").status_code == 200
    owner_id = scope["owners"][0]["id"]
    reviewer_id = scope["reviewer"]["id"]
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text("""
            UPDATE product_assessment
            SET status='completed', applicability='affected', analysis_summary='已审核结论',
                submitted_by=:owner_id, submitted_at=CURRENT_TIMESTAMP,
                review_decision='approved', reviewer_id=:reviewer_id,
                reviewed_at=CURRENT_TIMESTAMP
        """), {"owner_id": owner_id, "reviewer_id": reviewer_id})
    with client.app.state.database.session_factory.begin() as session:
        vulnerability = session.scalar(select(Vulnerability))
        changed = [dict(item) for item in vulnerability.affected_ranges_json]
        changed[0]["cpe"] = None
        vulnerability.affected_ranges_json = changed
        vulnerability.content_sha256 = "c" * 64

    changed = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches").json()
    repeated = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches").json()

    assert changed["task_generation"]["task_reassess_count"] == 1
    assert repeated["task_generation"]["task_reassess_count"] == 0
    rows = assessment_rows(client)
    assert len(rows) == 2
    previous, current = rows
    assert previous["status"] == "completed"
    assert previous["is_current"] == 0
    assert previous["analysis_summary"] == "已审核结论"
    assert previous["review_decision"] == "approved"
    assert current["revision_no"] == 2
    assert current["parent_revision_id"] == previous["id"]
    assert current["status"] == "reassess"
    assert current["is_current"] == 1
    assert current["analysis_summary"] == "已审核结论"
    assert current["submitted_by"] is None
    assert current["review_decision"] is None
    assert current["reviewer_id"] is None
    assert current["assessment_basis_sha256"]
    assert current["reassess_changes_json"]["trigger_type"] == "automatic_reassessment"
    assert "candidate" in current["reassess_changes_json"]["change_types"]


def test_candidate_removal_preserves_completed_history_and_creates_reassess(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text("UPDATE product_assessment SET status='completed'"))
    with client.app.state.database.session_factory.begin() as session:
        vulnerability = session.scalar(select(Vulnerability))
        changed = [dict(item) for item in vulnerability.affected_ranges_json]
        changed[0]["version"] = "4.0.0"
        vulnerability.affected_ranges_json = changed
        vulnerability.content_sha256 = "d" * 64

    result = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches").json()

    assert result["candidate_removed_count"] == 1
    assert result["task_generation"]["task_reassess_count"] == 1
    rows = assessment_rows(client)
    assert [row["status"] for row in rows] == ["completed", "reassess"]
    assert "候选已移除" in rows[-1]["reassess_reason"]


def test_non_material_source_change_does_not_create_reassess(client: TestClient) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text("UPDATE product_assessment SET status='completed'"))
    with client.app.state.database.session_factory.begin() as session:
        vulnerability = session.scalar(select(Vulnerability))
        vulnerability.description = "只修改来源描述，不改变候选证据"
        vulnerability.content_sha256 = "e" * 64

    result = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches").json()

    assert result["candidate_updated_count"] == 1
    assert result["task_generation"]["task_reassess_count"] == 0
    assert len(assessment_rows(client)) == 1


def test_submitted_assessment_merges_candidate_change_without_overwrite(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text(
            "UPDATE product_assessment SET status='submitted', analysis_summary='待审核内容'"
        ))
    with client.app.state.database.session_factory.begin() as session:
        vulnerability = session.scalar(select(Vulnerability))
        changed = [dict(item) for item in vulnerability.affected_ranges_json]
        changed[0]["cpe"] = None
        vulnerability.affected_ranges_json = changed
        vulnerability.content_sha256 = "f" * 64

    tasks = client.post(
        f"/api/v1/import-packages/{batch_id}/ots-matches"
    ).json()["task_generation"]

    assert tasks["task_updated_count"] == 1
    assert tasks["task_skipped_count"] == 0
    rows = assessment_rows(client)
    assert len(rows) == 1
    assert rows[0]["status"] == "submitted"
    assert rows[0]["analysis_summary"] == "待审核内容"
    assert rows[0]["row_version"] == 2
    assert "candidate" in rows[0]["reassess_changes_json"]["change_types"]


@pytest.mark.parametrize("status", ["pending", "returned", "reassess", "submitted"])
def test_in_progress_assessment_merges_change_without_revising_or_overwriting(
    client: TestClient, status: str
) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE product_assessment "
                "SET status=:status, analysis_summary='用户已填写内容', row_version=5"
            ),
            {"status": status},
        )
    with client.app.state.database.session_factory.begin() as session:
        vulnerability = session.scalar(select(Vulnerability))
        assert vulnerability is not None
        changed = [dict(item) for item in vulnerability.affected_ranges_json]
        changed[0]["cpe"] = None
        vulnerability.affected_ranges_json = changed
        vulnerability.content_sha256 = status * 16

    result = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")

    assert result.status_code == 200
    rows = assessment_rows(client)
    assert len(rows) == 1
    assert rows[0]["revision_no"] == 1
    assert rows[0]["status"] == status
    assert rows[0]["analysis_summary"] == "用户已填写内容"
    assert rows[0]["row_version"] == 6
    assert "candidate" in rows[0]["reassess_changes_json"]["change_types"]


def test_source_import_creates_reassessment_before_candidate_recalculation(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text(
            "UPDATE product_assessment SET status='completed', applicability='affected', analysis_summary='保留结论'"
        ))
    rows = base_rows()
    rows["nvd_cves.csv"][0]["vuln_status"] = "Rejected"
    rows["nvd_cves.csv"][0]["last_modified_at"] = "2026-08-03T00:00:00Z"
    import_package(
        client,
        build_package(
            rows=rows,
            batch_no="BATCH-20260823-001",
            source_release="fkie-cad/nvd-json-data-feeds@2026-08-23",
        ),
        "ots_intelligence_20260823_010203.zip",
    )

    assessments = assessment_rows(client)
    assert len(assessments) == 2
    assert assessments[0]["status"] == "completed"
    assert assessments[1]["status"] == "reassess"
    assert assessments[1]["analysis_summary"] == "保留结论"
    assert "source" in assessments[1]["reassess_changes_json"]["change_types"]
    detail = client.get(f"/api/v1/assessments/{assessments[1]['id']}")
    assert detail.status_code == 200
    reassessment = detail.json()["reassessment"]
    assert reassessment["trigger_type"] == "automatic_reassessment"
    assert reassessment["basis_sha256"] == assessments[1]["assessment_basis_sha256"]
    assert reassessment["change_types"] == ["source"]
    assert reassessment["changes"][0]["field"].startswith("source.")


def test_source_import_preview_reports_reassessment_without_writes(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text("UPDATE product_assessment SET status='completed'"))
    before = assessment_rows(client)
    rows = base_rows()
    rows["nvd_cves.csv"][0]["vuln_status"] = "Rejected"
    rows["nvd_cves.csv"][0]["last_modified_at"] = "2026-08-04T00:00:00Z"

    preview = client.post(
        "/api/v1/import-packages/validate",
        files={
            "file": (
                "ots_intelligence_20260824_010203.zip",
                build_package(
                    rows=rows,
                    batch_no="BATCH-20260824-001",
                    source_release="fkie-cad/nvd-json-data-feeds@2026-08-24",
                ),
                "application/zip",
            )
        },
    )

    assert preview.status_code == 201
    task_preview = preview.json()["source_reassessment"]
    assert task_preview["status"] == "pending"
    assert task_preview["task_reassess_count"] == 1
    assert task_preview["task_updated_count"] == 0
    assert assessment_rows(client) == before


def test_new_product_relation_creates_missing_task_from_existing_candidate(
    client: TestClient,
) -> None:
    login(client)
    owner = create_user(client, "late-relation-owner", ["product_owner"])
    reviewer = create_user(client, "late-relation-reviewer", ["reviewer"])
    ots = client.post(
        "/api/v1/ots-components",
        json={
            "ots_name": "OpenSSL",
            "ots_version": "3.0.0",
            "official_website": "https://openssl.org",
            "is_eol": False,
        },
    ).json()
    batch_id = import_batch(client)
    matched = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches").json()
    assert matched["task_generation"]["task_inserted_count"] == 0
    product = client.post(
        "/api/v1/products", json={"product_code": "P-LINK", "product_name": "后关联产品"}
    ).json()
    version = client.post(
        f"/api/v1/products/{product['id']}/versions",
        json={"version_no": "1.0", "owner_id": owner["id"], "reviewer_id": reviewer["id"]},
    ).json()

    relation = client.post(
        f"/api/v1/product-versions/{version['id']}/ots",
        json={"ots_component_id": ots["id"]},
    )

    assert relation.status_code == 201
    assessments = assessment_rows(client)
    assert len(assessments) == 1
    assert assessments[0]["product_ots_id"] == relation.json()["id"]
    assert assessments[0]["status"] == "pending"
    assert assessments[0]["assessment_basis_sha256"]


def test_product_relation_disable_and_restore_merge_context_change(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    client.post(f"/api/v1/import-packages/{scope['batch_id']}/ots-matches")
    relation = scope["scopes"][0][2]
    version = scope["scopes"][0][1]
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text("UPDATE product_assessment SET status='completed'"))

    disabled = client.post(
        f"/api/v1/product-versions/{version['id']}/ots/{relation['id']}/disable",
        json={"row_version": relation["row_version"]},
    ).json()
    after_disable = assessment_rows(client)
    assert len(after_disable) == 2
    assert after_disable[-1]["status"] == "reassess"
    assert "product_context" in after_disable[-1]["reassess_changes_json"]["change_types"]

    client.post(
        f"/api/v1/product-versions/{version['id']}/ots/{relation['id']}/restore",
        json={"row_version": disabled["row_version"]},
    )
    after_restore = assessment_rows(client)
    assert len(after_restore) == 2
    assert after_restore[-1]["status"] == "reassess"
    assert after_restore[-1]["reassess_changes_json"] is None


def test_old_matching_result_is_exposed_as_pending_task_generation(
    client: TestClient,
) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    with client.app.state.database.session_factory.begin() as session:
        batch = session.get(ImportBatch, batch_id)
        root = dict(batch.result_json)
        matching = dict(root["matching"])
        matching.pop("task_generation", None)
        root["matching"] = matching
        batch.result_json = root

    result = client.get(f"/api/v1/import-packages/{batch_id}/ots-match-result")

    assert result.status_code == 200
    assert result.json()["task_generation"]["status"] == "pending"


def test_task_changes_write_one_bounded_audit_summary(client: TestClient) -> None:
    scope = setup_scope(client, product_count=2)
    batch_id = scope["batch_id"]

    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")
    client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")

    with client.app.state.database.session_factory() as session:
        audits = session.scalars(
            select(AuditLog).where(AuditLog.object_type == "product_assessment")
        ).all()
        assert len(audits) == 1
        assert audits[0].action == "batch_upsert"
        assert audits[0].detail_json["task_inserted_count"] == 2
        assert audits[0].detail_json["entrypoint"] == "candidate"
        assert len(audits[0].detail_json["basis_fingerprints"]) == 2
        assert audits[0].detail_json["revision_links"] == []
        assert "analysis_summary" not in audits[0].detail_json
        assert "assessment_basis_json" not in audits[0].detail_json
        assert session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.object_type == "product_assessment"
            )
        ) == 1


def test_task_stage_failure_rolls_back_candidates_tasks_and_audits(
    client: TestClient, monkeypatch
) -> None:
    scope = setup_scope(client)
    batch_id = scope["batch_id"]
    service = client.app.state.vulnerability_matching_service

    def fail_task_write(*_args, **_kwargs) -> None:
        raise RuntimeError("task write failed")

    monkeypatch.setattr(service._assessment_tasks, "apply", fail_task_write)
    failed = client.post(f"/api/v1/import-packages/{batch_id}/ots-matches")

    assert failed.status_code == 500
    assert failed.json()["code"] == "MATCH_EXECUTION_FAILED"
    with client.app.state.database.engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM vulnerability_ots_match")) == 0
        assert connection.scalar(text("SELECT COUNT(*) FROM product_assessment")) == 0
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(func.count(AuditLog.id))) is not None
        assert session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.object_type.in_(["vulnerability_ots_match", "product_assessment"])
            )
        ) == 0
    result = client.get(f"/api/v1/import-packages/{batch_id}/ots-match-result").json()
    assert result["status"] == "failed"
    assert result["task_generation"]["status"] == "failed"
    assert result["task_generation"]["task_failed_count"] == 1
