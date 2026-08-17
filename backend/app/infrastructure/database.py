from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, database_url: str | None) -> None:
        self._engine: Engine | None = create_engine(database_url, pool_pre_ping=True) if database_url else None
        self.session_factory = sessionmaker(bind=self._engine, expire_on_commit=False) if self._engine else None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("数据库未配置")
        return self._engine

    def session(self) -> Session:
        if self.session_factory is None:
            raise RuntimeError("数据库未配置")
        return self.session_factory()

    def check(self) -> bool:
        if self._engine is None:
            return False
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
