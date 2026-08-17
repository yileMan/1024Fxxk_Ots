from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class Migration:
    version: int
    path: Path
    sql: str


def discover_migrations(directory: Path) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        match = re.match(r"(\d{3})_", path.name)
        if match is None:
            continue
        migrations.append(Migration(int(match.group(1)), path, path.read_text(encoding="utf-8")))
    return migrations


def apply_migrations(engine: Engine, directory: Path) -> list[int]:
    """Apply each unapplied migration and return the versions applied in this run."""
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migration (version INTEGER PRIMARY KEY, checksum VARCHAR(64) NOT NULL, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL)"))
        applied = {row[0] for row in connection.execute(text("SELECT version FROM schema_migration"))}

    completed: list[int] = []
    for migration in discover_migrations(directory):
        if migration.version in applied:
            continue
        checksum = hashlib.sha256(migration.sql.encode()).hexdigest()
        with engine.begin() as connection:
            connection.execute(text(migration.sql))
            connection.execute(text("INSERT INTO schema_migration (version, checksum) VALUES (:version, :checksum)"), {"version": migration.version, "checksum": checksum})
        completed.append(migration.version)
    return completed
