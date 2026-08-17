from app.infrastructure.settings import Settings


def test_settings_load_database_url_from_yaml(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "database:\n  url: mysql+pymysql://root:password@localhost:3306/ots_test?charset=utf8mb4\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OTS_DATABASE_URL", raising=False)
    monkeypatch.setenv("OTS_AUTH_SECRET", "test-secret-that-is-long-enough-for-authentication")

    settings = Settings.from_environment(config)

    assert settings.database_url == "mysql+pymysql://root:password@localhost:3306/ots_test?charset=utf8mb4"


def test_environment_variable_overrides_yaml(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("database:\n  url: mysql+pymysql://yaml\n", encoding="utf-8")
    monkeypatch.setenv("OTS_DATABASE_URL", "mysql+pymysql://environment")
    monkeypatch.setenv("OTS_AUTH_SECRET", "test-secret-that-is-long-enough-for-authentication")

    assert Settings.from_environment(config).database_url == "mysql+pymysql://environment"


def test_settings_load_authentication_values_from_yaml(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "database:\n  url: mysql+pymysql://database\nauthentication:\n  secret: yaml-secret-that-is-long-enough-for-authentication\n  allowed_origin: http://localhost:5173\n  cookie_secure: false\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OTS_AUTH_SECRET", raising=False)
    monkeypatch.delenv("OTS_ALLOWED_ORIGIN", raising=False)
    monkeypatch.delenv("OTS_COOKIE_SECURE", raising=False)

    settings = Settings.from_environment(config)

    assert settings.auth_secret == "yaml-secret-that-is-long-enough-for-authentication"
    assert settings.allowed_origin == "http://localhost:5173"
    assert settings.cookie_secure is False


def test_production_rejects_missing_or_short_auth_secret(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("database:\n  url: mysql+pymysql://database\n", encoding="utf-8")
    monkeypatch.setenv("OTS_ENV", "production")
    monkeypatch.setenv("OTS_AUTH_SECRET", "short")

    try:
        Settings.from_environment(config)
    except RuntimeError as error:
        assert "OTS_AUTH_SECRET" in str(error)
    else:
        raise AssertionError("生产环境必须拒绝短认证密钥")


def test_database_configuration_rejects_missing_auth_secret_in_development(tmp_path, monkeypatch) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("database:\n  url: mysql+pymysql://database\n", encoding="utf-8")
    monkeypatch.delenv("OTS_AUTH_SECRET", raising=False)
    monkeypatch.setenv("OTS_ENV", "development")

    try:
        Settings.from_environment(config)
    except RuntimeError as error:
        assert "OTS_AUTH_SECRET" in str(error)
    else:
        raise AssertionError("认证启用时必须拒绝缺失签名密钥")
