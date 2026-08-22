import pytest

from app.infrastructure.settings import Settings


def test_settings_load_database_url_from_yaml_without_authentication_config(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "database:\n  url: mysql+pymysql://root:password@localhost:3306/ots_test?charset=utf8mb4\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OTS_DATABASE_URL", raising=False)

    settings = Settings.from_environment(config)

    assert settings.database_url == "mysql+pymysql://root:password@localhost:3306/ots_test?charset=utf8mb4"


def test_environment_variable_overrides_yaml(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("database:\n  url: mysql+pymysql://yaml\n", encoding="utf-8")
    monkeypatch.setenv("OTS_DATABASE_URL", "mysql+pymysql://environment")

    assert Settings.from_environment(config).database_url == "mysql+pymysql://environment"


def test_import_package_settings_have_safe_defaults_and_environment_overrides(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")
    temp_dir = tmp_path / "custom-incoming"
    archive_dir = tmp_path / "custom-archive"
    monkeypatch.setenv("OTS_IMPORT_TEMP_DIR", str(temp_dir))
    monkeypatch.setenv("OTS_IMPORT_ARCHIVE_DIR", str(archive_dir))

    settings = Settings.from_environment(config)

    assert settings.import_temp_dir == temp_dir.resolve()
    assert settings.import_archive_dir == archive_dir.resolve()
    assert settings.import_max_upload_bytes == 50 * 1024 * 1024
    assert settings.import_max_member_bytes == 50 * 1024 * 1024
    assert settings.import_max_total_bytes == 200 * 1024 * 1024
    assert settings.import_max_compression_ratio == 100
    assert settings.import_max_csv_rows == 10_000
    assert settings.import_max_field_bytes == 64 * 1024
    assert settings.import_max_errors == 1_000


def test_import_package_limits_reject_non_positive_values(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("OTS_IMPORT_MAX_UPLOAD_BYTES", "0")

    with pytest.raises(RuntimeError, match="OTS_IMPORT_MAX_UPLOAD_BYTES"):
        Settings.from_environment(config)


def test_production_requires_database_but_not_authentication_secret(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("database:\n  url: mysql+pymysql://database\n", encoding="utf-8")
    monkeypatch.setenv("OTS_ENV", "production")
    assert Settings.from_environment(config).database_url == "mysql+pymysql://database"


def test_production_rejects_missing_database(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("OTS_ENV", "production")
    monkeypatch.delenv("OTS_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="OTS_DATABASE_URL"):
        Settings.from_environment(config)
