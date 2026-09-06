from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import make_url

from app.infrastructure.settings import Settings
from app.migrations import apply_migrations
from app.models.user import AuditLog
from app.services.audit_operations import AuditOperationsService
from app.services.authentication import AuthenticationService


def test_mysql_ten_year_audit_pagination_plans_and_concurrency() -> None:
    configured_url = Settings.from_environment().database_url
    assert configured_url is not None
    url = make_url(configured_url)
    database_name = f"ots21_test_{uuid4().hex}"
    admin_engine = create_engine(url.set(database="mysql"))
    test_engine = None
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f"CREATE DATABASE `{database_name}` CHARACTER SET utf8mb4"))
        test_url = url.set(database=database_name)
        test_engine = create_engine(test_url, pool_size=20, max_overflow=5)
        versions = apply_migrations(test_engine, Path(__file__).parents[1] / "migrations")
        assert versions == list(range(1, 14))
        from sqlalchemy.orm import sessionmaker
        session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
        AuthenticationService(session_factory).initialize_admin("admin", "管理员", "admin-password")
        start = datetime(2016, 1, 1, tzinfo=UTC)
        rows = []
        actions = ("insert", "update", "delete", "batch_upsert")
        objects = ("product", "product_version", "ots_component", "product_assessment")
        for index in range(5_000):
            rows.append({
                "user_id": 1 if index % 5 else None,
                "action": actions[index % len(actions)],
                "object_type": objects[index % len(objects)],
                "object_id": str(index % 300) if index % 5 else None,
                "detail_json": {"schema_version": "1.0", "sequence": index},
                "created_at": start + timedelta(days=index % 3653, milliseconds=index % 3),
            })
        with test_engine.begin() as connection:
            connection.execute(insert(AuditLog), rows)
            table_count = connection.scalar(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema=:schema AND table_name <> 'schema_migration'"
            ), {"schema": database_name})
            assert table_count == 11
            plans = {}
            queries = {
                "unfiltered": "SELECT id FROM audit_log ORDER BY created_at DESC, id DESC LIMIT 20",
                "user_time": "SELECT id FROM audit_log WHERE user_id=1 AND created_at >= '2025-01-01' ORDER BY created_at DESC, id DESC LIMIT 20",
                "object_time": "SELECT id FROM audit_log WHERE object_type='product' AND created_at >= '2025-01-01' ORDER BY created_at DESC, id DESC LIMIT 20",
                "action_time": "SELECT id FROM audit_log WHERE action='update' AND created_at >= '2025-01-01' ORDER BY created_at DESC, id DESC LIMIT 20",
            }
            for name, statement in queries.items():
                plans[name] = [dict(row._mapping) for row in connection.execute(text(f"EXPLAIN {statement}"))]
            print(f"ots21_audit_explain={plans}")

        service = AuditOperationsService(session_factory)
        page = service.list_logs(
            object_type=None, user_id=None, action=None, created_from=None, created_to=None,
            cursor=None, limit=20,
        )
        assert page["total"] == 5_000
        assert len(page["items"]) == 20 and page["next_cursor"]
        second = service.list_logs(
            object_type=None, user_id=None, action=None, created_from=None, created_to=None,
            cursor=page["next_cursor"], limit=20,
        )
        assert {item["id"] for item in page["items"]}.isdisjoint(
            {item["id"] for item in second["items"]}
        )

        started = perf_counter()
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(
                lambda _: service.list_logs(
                    object_type="product", user_id=None, action=None,
                    created_from=None, created_to=None, cursor=None, limit=20,
                ),
                range(20),
            ))
        elapsed = perf_counter() - started
        print(f"ots21_audit_concurrency users=20 p95_upper_seconds={elapsed:.3f}")
        assert all(result["items"] for result in results)
        assert elapsed < 3
    finally:
        if test_engine is not None:
            test_engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{database_name}`"))
        admin_engine.dispose()
