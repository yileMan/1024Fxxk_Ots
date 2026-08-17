import logging

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_service_and_database_status(monkeypatch) -> None:
    application = create_app()
    monkeypatch.setattr(application.state.database, "check", lambda: True)

    response = TestClient(application).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"service": "available", "database": "available"}


def test_health_hides_database_error(monkeypatch) -> None:
    application = create_app()
    monkeypatch.setattr(application.state.database, "check", lambda: False)

    response = TestClient(application).get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
    assert "password" not in response.text.lower()


def test_unknown_api_route_uses_standard_error_response() -> None:
    response = TestClient(create_app()).get("/api/v1/unknown")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    assert response.headers["x-correlation-id"] == response.json()["correlation_id"]


def test_request_log_does_not_include_sensitive_headers(caplog) -> None:
    caplog.set_level(logging.INFO)

    response = TestClient(create_app()).get(
        "/api/v1/unknown", headers={"Authorization": "Bearer secret-token"}
    )

    assert response.status_code == 404
    assert "secret-token" not in caplog.text
