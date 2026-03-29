"""Tests for auth routes and JWT helpers."""

from unittest.mock import AsyncMock, MagicMock, patch


def test_version(client):
    resp = client.get("/version")
    assert resp.status_code == 200
    assert "version" in resp.json()


def test_auth_me(client, auth_headers, user):
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == user["email"]
    assert data["name"] == user["name"]
    assert "id" in data


def test_auth_me_invalid_token(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401


def test_auth_me_token_missing_sub(client):
    from datetime import UTC, datetime, timedelta

    from jose import jwt

    from main import JWT_ALGORITHM, JWT_SECRET

    # Token with no 'sub' claim
    bad_token = jwt.encode(
        {"email": "x@x.com", "exp": datetime.now(UTC) + timedelta(days=1)},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
    assert resp.status_code == 401


def test_auth_me_user_not_in_db(client):
    from main import create_jwt

    token = create_jwt("nonexistent-id", "ghost@example.com")
    resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_auth_login_redirects(client):
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "accounts.google.com" in resp.headers["location"]


def test_auth_callback(client, aws):
    mock_token_resp = MagicMock()
    mock_token_resp.raise_for_status = MagicMock()
    mock_token_resp.json.return_value = {"access_token": "fake-access-token"}

    mock_userinfo_resp = MagicMock()
    mock_userinfo_resp.raise_for_status = MagicMock()
    mock_userinfo_resp.json.return_value = {
        "sub": "google-callback-123",
        "email": "callback@example.com",
        "name": "Callback User",
        "picture": "https://example.com/pic.jpg",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_token_resp)
    mock_client.get = AsyncMock(return_value=mock_userinfo_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("main.httpx.AsyncClient", return_value=mock_client):
        resp = client.get("/auth/callback?code=fake-code", follow_redirects=False)

    assert resp.status_code in (302, 307)
    assert "token=" in resp.headers["location"]


def test_dev_login_disabled_by_default(client):
    resp = client.post(
        "/auth/dev-login",
        json={"email": "test@example.com"},
    )
    assert resp.status_code == 404


def test_dev_login_enabled(client, aws, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_LOGIN", "true")
    resp = client.post(
        "/auth/dev-login",
        json={"email": "devuser@example.com", "name": "Dev User"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["email"] == "devuser@example.com"
