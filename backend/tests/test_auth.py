from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.user import AppUser, Base
from app.services.authentication import AuthenticationService, PasswordPolicyError


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    database_path = tmp_path / "auth.db"
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("OTS_AUTH_SECRET", "test-secret-that-is-long-enough-for-authentication")
    monkeypatch.setenv("OTS_ALLOWED_ORIGIN", "http://testserver")
    application = create_app()
    Base.metadata.create_all(application.state.database.engine)
    return TestClient(application)


def test_initialize_admin_creates_only_one_user(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)

    created = service.initialize_admin("admin", "初始管理员", "long-enough-password")
    repeated = service.initialize_admin("admin", "另一名称", "another-long-password")

    assert created.login_name == "admin"
    assert created.roles == ["admin"]
    assert repeated is None


def test_initialize_admin_rejects_short_password(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)

    with pytest.raises(PasswordPolicyError):
        service.initialize_admin("admin", "初始管理员", "short")


def test_login_sets_secure_session_and_updates_last_login(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")

    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "long-enough-password"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    assert response.json()["login_name"] == "admin"
    assert "ots_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    with client.app.state.database.session_factory() as session:
        assert session.get(AppUser, 1).last_login_at is not None


@pytest.mark.parametrize(
    ("login_name", "password"),
    [("unknown", "long-enough-password"), ("admin", "wrong-password")],
)
def test_login_does_not_disclose_invalid_credentials(
    client: TestClient, login_name: str, password: str
) -> None:
    AuthenticationService(client.app.state.database.session_factory).initialize_admin(
        "admin", "初始管理员", "long-enough-password"
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": login_name, "password": password},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers


def test_disabled_user_loses_an_existing_session(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "long-enough-password"},
        headers={"Origin": "http://testserver"},
    )
    with client.app.state.database.session_factory.begin() as session:
        session.get(AppUser, 1).status = "disabled"

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_USER_DISABLED"
    assert "ots_session=" in response.headers["set-cookie"]


def test_invalid_or_expired_cookie_is_cleared(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")
    token = service.create_session_token(1, datetime.now(timezone.utc) - timedelta(hours=3))
    client.cookies.set("ots_session", token)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_SESSION_INVALID"
    assert "ots_session=" in response.headers["set-cookie"]


def test_logout_is_idempotent_and_auth_actions_do_not_write_audit_log(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "long-enough-password"},
        headers={"Origin": "http://testserver"},
    )

    response = client.post("/api/v1/auth/logout", headers={"Origin": "http://testserver"})
    second_response = client.post("/api/v1/auth/logout", headers={"Origin": "http://testserver"})

    assert response.status_code == 204
    assert second_response.status_code == 204
    with client.app.state.database.session_factory() as session:
        assert session.execute("SELECT COUNT(*) FROM audit_log").scalar_one() == 0


def test_write_requests_reject_an_untrusted_origin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "long-enough-password"},
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "AUTH_ORIGIN_REJECTED"
