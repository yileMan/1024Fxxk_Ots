from pathlib import Path

from sqlalchemy import create_engine

from app.migrations import apply_migrations, discover_migrations


def test_migrations_are_numbered_and_create_only_baseline_business_tables() -> None:
    migrations = discover_migrations(Path(__file__).parents[1] / "migrations")

    assert [migration.version for migration in migrations] == [1, 2, 3, 4, 5, 6, 7, 8]
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


def test_migrations_apply_once(tmp_path) -> None:
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "001_example.sql").write_text("CREATE TABLE example (id INTEGER PRIMARY KEY);", encoding="utf-8")
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")

    assert apply_migrations(engine, migration_dir) == [1]
    assert apply_migrations(engine, migration_dir) == []
    engine.dispose()
