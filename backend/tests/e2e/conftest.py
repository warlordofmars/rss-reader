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
