from dataclasses import dataclass
import os
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Settings:
    database_url: str | None

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
        database_url = os.getenv("OTS_DATABASE_URL") or file_url
        if database_url is not None and not isinstance(database_url, str):
            raise RuntimeError("database.url 必须是字符串")
        if environment == "production" and not database_url:
            raise RuntimeError("生产环境缺少 OTS_DATABASE_URL 配置")
        return cls(
            database_url=database_url,
        )
