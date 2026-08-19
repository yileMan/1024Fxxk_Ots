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
