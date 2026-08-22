from pathlib import Path

from sqlalchemy import create_engine

from app.migrations import apply_migrations, discover_migrations


def test_migrations_are_numbered_and_create_only_baseline_business_tables() -> None:
    migrations = discover_migrations(Path(__file__).parents[1] / "migrations")

    assert [migration.version for migration in migrations] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert "app_user" in migrations[1].sql
    assert "audit_log" not in migrations[1].sql
    assert "audit_log" in migrations[2].sql
    assert "product" in migrations[3].sql
    assert "product_version" in migrations[4].sql
    assert "ots_component" in migrations[5].sql
    assert "product_ots" in migrations[6].sql
    assert "user_product_scope" in migrations[7].sql
    assert "uk_user_product_scope" in migrations[7].sql
    assert "idx_scope_product" in migrations[7].sql
    assert "idx_scope_version" in migrations[7].sql
    assert "status" not in migrations[5].sql
    assert "import_batch" in migrations[8].sql
    assert "scope_coverage_json" in migrations[8].sql
    assert "manifest_json" in migrations[8].sql
    assert "uk_import_batch_no" in migrations[8].sql
    assert "uk_import_package_sha" in migrations[8].sql
    assert "idx_import_status_time" in migrations[8].sql
    assert "idx_import_covered_to" in migrations[8].sql

    rollback = (Path(__file__).parents[1] / "migrations" / "008_user_product_scope.rollback.md").read_text(encoding="utf-8")
    assert "备份" in rollback
    assert "DROP TABLE user_product_scope" in rollback
    assert "级联删除" in rollback

    import_rollback = (Path(__file__).parents[1] / "migrations" / "009_import_batch.rollback.md").read_text(encoding="utf-8")
    assert "备份" in import_rollback
    assert "表为空" in import_rollback
    assert "DROP TABLE import_batch" in import_rollback
    assert "级联" in import_rollback


def test_migrations_apply_once(tmp_path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_example.sql").write_text("CREATE TABLE example (id INTEGER PRIMARY KEY);", encoding="utf-8")
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")

    assert apply_migrations(engine, migration_dir) == [1]
    assert apply_migrations(engine, migration_dir) == []
    engine.dispose()
