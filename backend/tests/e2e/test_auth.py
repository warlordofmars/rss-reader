import httpx


def test_dev_login(base_url):
    resp = httpx.post(
        f"{base_url}/auth/dev-login",
        json={"email": "auth-test@example.com", "name": "Auth Test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["email"] == "auth-test@example.com"


def test_me(base_url, auth_headers):
    resp = httpx.get(f"{base_url}/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "e2e-test@example.com"
    assert data["name"] == "E2E Test User"


def test_me_unauthenticated(base_url):
    resp = httpx.get(f"{base_url}/auth/me")
    assert resp.status_code == 403


def test_me_bad_token(base_url):
    resp = httpx.get(f"{base_url}/auth/me", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401


def test_dev_login_disabled_without_flag(base_url):
    """
    This test is a no-op against dev (where the flag IS set),
    but serves as documentation that the endpoint must 404 on prod.
    Skipped unless explicitly targeting prod.
    """
    import os
    if os.environ.get("E2E_BASE_URL", "").find("api.rss.warlordofmars") != -1:
        resp = httpx.post(
            f"{base_url}/auth/dev-login",
            json={"email": "should-fail@example.com"},
        )
        assert resp.status_code == 404
