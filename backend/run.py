import uvicorn
from pathlib import Path
import sys

from sqlalchemy import create_engine

from app.infrastructure.settings import Settings
from app.migrations import apply_migrations


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "migrate":
        settings = Settings.from_environment()
        if not settings.database_url:
            raise SystemExit("缺少 OTS_DATABASE_URL，无法执行迁移")
        versions = apply_migrations(create_engine(settings.database_url), Path(__file__).parent / "migrations")
        print(f"已执行迁移: {versions or '无'}")
        raise SystemExit(0)
    uvicorn.run("app.main:app", host="localhost", port=5353, reload=True)
