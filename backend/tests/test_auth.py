import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.models.user import AppUser, Base
from app.services.authentication import AuthenticationService


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "auth.db"
    monkeypatch.setenv("OTS_DATABASE_URL", f"sqlite:///{database_path}")
    application = create_app()
    Base.metadata.create_all(application.state.database.engine)
    with TestClient(application) as test_client:
        yield test_client
    application.state.database.engine.dispose()


def test_initialize_admin_creates_only_one_user(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)

    created = service.initialize_admin("admin", "初始管理员", "long-enough-password")
    repeated = service.initialize_admin("admin", "另一名称", "another-long-password")

    assert created.login_name == "admin"
    assert created.roles == ["admin"]
    assert repeated is None


def test_initialize_admin_accepts_short_password(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    assert service.initialize_admin("admin", "初始管理员", "short") is not None


def test_login_accepts_empty_password_when_it_matches(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "")

    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": ""},
    )

    assert response.status_code == 200


def test_login_sets_user_id_cookie_without_origin_validation(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")

    response = client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "long-enough-password"},
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 200
    assert response.json()["login_name"] == "admin"
    assert "ots_user_id=1" in response.headers["set-cookie"]
    assert "max-age" not in response.headers["set-cookie"].lower()


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
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers


def test_disabled_user_is_resolved_from_user_id_cookie(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")
    client.post(
        "/api/v1/auth/login",
        json={"login_name": "admin", "password": "long-enough-password"},
    )
    with client.app.state.database.session_factory.begin() as session:
        session.get(AppUser, 1).status = "disabled"

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["login_name"] == "admin"


def test_unknown_user_id_cookie_is_rejected(client: TestClient) -> None:
    service = AuthenticationService(client.app.state.database.session_factory)
    service.initialize_admin("admin", "初始管理员", "long-enough-password")
    client.cookies.set("ots_user_id", "999")

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_SESSION_INVALID"
