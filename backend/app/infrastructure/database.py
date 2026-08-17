from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


class Database:
    def __init__(self, database_url: str | None) -> None:
        self._engine: Engine | None = create_engine(database_url, pool_pre_ping=True) if database_url else None

    def check(self) -> bool:
        if self._engine is None:
            return False
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
