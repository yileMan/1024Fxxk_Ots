from app.infrastructure.settings import Settings


def test_settings_load_database_url_from_yaml(tmp_path, monkeypatch) -> None:
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
