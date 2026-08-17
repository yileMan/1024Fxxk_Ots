import getpass
import json
import os
from pathlib import Path
import sys

import uvicorn

from sqlalchemy import create_engine

from app.infrastructure.database import Database
from app.infrastructure.settings import Settings
from app.main import app
from app.migrations import apply_migrations
from app.services.authentication import AuthenticationService


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "migrate":
        settings = Settings.from_environment()
        if not settings.database_url:
            raise SystemExit("缺少 OTS_DATABASE_URL，无法执行迁移")
        versions = apply_migrations(create_engine(settings.database_url), Path(__file__).parent / "migrations")
        print(f"已执行迁移: {versions or '无'}")
        raise SystemExit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "export-openapi":
        output_path = Path(sys.argv[2])
        output_path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已导出 OpenAPI: {output_path}")
        raise SystemExit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "initialize-admin":
        settings = Settings.from_environment()
        if not settings.database_url:
            raise SystemExit("缺少 OTS_DATABASE_URL，无法初始化管理员")
        password = os.getenv("OTS_INITIAL_ADMIN_PASSWORD") or getpass.getpass("初始管理员密码: ")
        database = Database(settings.database_url)
        if database.session_factory is None:
            raise SystemExit("数据库未配置")
        user = AuthenticationService(
            database.session_factory,
            settings.auth_secret,
        ).initialize_admin(sys.argv[2], sys.argv[3], password)
        print("管理员已存在" if user is None else f"管理员已初始化：{user.login_name}")
        raise SystemExit(0)
    uvicorn.run("app.main:app", host="localhost", port=5353, reload=True)
