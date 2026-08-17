from dataclasses import dataclass
import os
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    auth_secret: str | None
    allowed_origin: str
    cookie_secure: bool

    @classmethod
    def from_environment(cls, config_path: Path | None = None) -> "Settings":
        environment = os.getenv("OTS_ENV", "development")
        path = config_path or Path(__file__).parents[2] / "config.yaml"
        file_config: dict[str, object] = {}
        if path.exists():
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                file_config = loaded
        database = file_config.get("database", {})
        file_url = database.get("url") if isinstance(database, dict) else None
        authentication = file_config.get("authentication", {})
        file_secret = authentication.get("secret") if isinstance(authentication, dict) else None
        file_allowed_origin = authentication.get("allowed_origin") if isinstance(authentication, dict) else None
        file_cookie_secure = authentication.get("cookie_secure") if isinstance(authentication, dict) else None
        database_url = os.getenv("OTS_DATABASE_URL") or file_url
        if database_url is not None and not isinstance(database_url, str):
            raise RuntimeError("database.url 必须是字符串")
        if environment == "production" and not database_url:
            raise RuntimeError("生产环境缺少 OTS_DATABASE_URL 配置")
        auth_secret = os.getenv("OTS_AUTH_SECRET") or file_secret
        if auth_secret is not None and not isinstance(auth_secret, str):
            raise RuntimeError("authentication.secret 必须是字符串")
        if database_url and (auth_secret is None or len(auth_secret) < 32):
            raise RuntimeError("认证启用时必须配置至少 32 个字符的 OTS_AUTH_SECRET")
        allowed_origin = os.getenv("OTS_ALLOWED_ORIGIN") or file_allowed_origin or "http://localhost:5173"
        if not isinstance(allowed_origin, str):
            raise RuntimeError("authentication.allowed_origin 必须是字符串")
        cookie_secure_value = os.getenv("OTS_COOKIE_SECURE")
        if cookie_secure_value is None:
            cookie_secure = file_cookie_secure if isinstance(file_cookie_secure, bool) else environment == "production"
        else:
            cookie_secure = cookie_secure_value.lower() == "true"
        return cls(
            database_url=database_url,
            auth_secret=auth_secret,
            allowed_origin=allowed_origin,
            cookie_secure=cookie_secure,
        )
