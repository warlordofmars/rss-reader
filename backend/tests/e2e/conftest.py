"""
E2E test fixtures.

Runs against a live deployed environment. Requires:
  E2E_BASE_URL    — e.g. https://api.rss-dev.warlordofmars.net
  E2E_ADMIN_PASS  — admin HTTP Basic Auth password

The target environment must have ALLOW_DEV_LOGIN=true in its Lambda config.
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
ADMIN_PASS = os.environ.get("E2E_ADMIN_PASS", "admin")


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def admin_auth():
    return ("admin", ADMIN_PASS)


@pytest.fixture(scope="session")
def dev_user(base_url):
    """Create a test user via dev-login and return (headers, user) for the session."""
    resp = httpx.post(
        f"{base_url}/auth/dev-login",
        json={"email": "e2e-test@example.com", "name": "E2E Test User"},
    )
    assert resp.status_code == 200, f"dev-login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    headers = {"Authorization": f"Bearer {data['token']}"}
    return headers, data["user"]


@pytest.fixture(scope="session")
def auth_headers(dev_user):
    headers, _ = dev_user
    return headers


@pytest.fixture(scope="session")
def e2e_user(dev_user):
    _, user = dev_user
    return user


@pytest.fixture(scope="session", autouse=True)
def cleanup_all_feeds(base_url):
    """Delete all feeds for the e2e test user before the session starts.

    Skipped when ALLOW_DEV_LOGIN is unavailable (e.g. prod smoke tests).
    """
    import httpx as _httpx

    # Attempt dev-login; skip cleanup silently if the endpoint is disabled
    r = _httpx.post(
        f"{base_url}/auth/dev-login",
        json={"email": "e2e-test@example.com", "name": "E2E Test User"},
    )
    if r.status_code != 200:
        yield
        return
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    resp = _httpx.get(f"{base_url}/feeds", headers=headers)
    if resp.status_code == 200:
        for feed in resp.json():
            _httpx.delete(f"{base_url}/feeds/{feed['id']}", headers=headers)
    yield
