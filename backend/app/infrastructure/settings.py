from dataclasses import dataclass
import os
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    import_temp_dir: Path
    import_archive_dir: Path
    import_max_upload_bytes: int
    import_max_member_bytes: int
    import_max_total_bytes: int
    import_max_compression_ratio: float
    import_max_csv_rows: int
    import_max_field_bytes: int
    import_max_errors: int

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
        runtime_dir = Path(__file__).parents[2] / "var" / "imports"

        def positive_int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None:
                return default
            try:
                value = int(raw)
            except ValueError as error:
                raise RuntimeError(f"{name} 必须是正整数") from error
            if value <= 0:
                raise RuntimeError(f"{name} 必须是正整数")
            return value

        def positive_float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None:
                return default
            try:
                value = float(raw)
            except ValueError as error:
                raise RuntimeError(f"{name} 必须是正数") from error
            if value <= 0:
                raise RuntimeError(f"{name} 必须是正数")
            return value

        return cls(
            database_url=database_url,
            import_temp_dir=Path(os.getenv("OTS_IMPORT_TEMP_DIR", runtime_dir / "incoming")).resolve(),
            import_archive_dir=Path(os.getenv("OTS_IMPORT_ARCHIVE_DIR", runtime_dir / "archive")).resolve(),
            import_max_upload_bytes=positive_int("OTS_IMPORT_MAX_UPLOAD_BYTES", 50 * 1024 * 1024),
            import_max_member_bytes=positive_int("OTS_IMPORT_MAX_MEMBER_BYTES", 50 * 1024 * 1024),
            import_max_total_bytes=positive_int("OTS_IMPORT_MAX_TOTAL_BYTES", 200 * 1024 * 1024),
            import_max_compression_ratio=positive_float("OTS_IMPORT_MAX_COMPRESSION_RATIO", 100.0),
            import_max_csv_rows=positive_int("OTS_IMPORT_MAX_CSV_ROWS", 10_000),
            import_max_field_bytes=positive_int("OTS_IMPORT_MAX_FIELD_BYTES", 1024 * 1024),
            import_max_errors=positive_int("OTS_IMPORT_MAX_ERRORS", 1_000),
        )
