"""
Smoke tests — run against any environment, including prod.

These tests require NO authenticated user session (no dev-login) so they
work on prod where ALLOW_DEV_LOGIN is not set. They verify the deployment
is healthy: Lambda is up, DynamoDB is reachable, auth is wired, and admin
credentials work.
"""

import httpx
import pytest


def test_version(base_url):
    """Lambda is up and returning a version string."""
    resp = httpx.get(f"{base_url}/version", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert data["version"] != ""


def test_auth_login_redirects_to_google(base_url):
    """OAuth login redirects to Google — confirms client ID is configured."""
    resp = httpx.get(f"{base_url}/auth/login", follow_redirects=False, timeout=10)
    assert resp.status_code in (302, 307)
    location = resp.headers.get("location", "")
    assert "accounts.google.com" in location
    assert "client_id=" in location


def test_admin_auth_required(base_url):
    """Admin endpoint rejects unauthenticated requests."""
    resp = httpx.get(f"{base_url}/admin/users", timeout=10)
    assert resp.status_code == 401


def test_admin_reachable(base_url, admin_auth):
    """Admin endpoint is reachable with correct credentials and DynamoDB responds."""
    resp = httpx.get(f"{base_url}/admin/users", auth=admin_auth, timeout=10)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_admin_infra_has_cloudwatch_links(base_url, admin_auth):
    """On a deployed environment, infra links should be present."""
    resp = httpx.get(f"{base_url}/admin/infra", auth=admin_auth, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    # On Lambda, both dashboard and lambda_logs should be set
    import os
    if os.environ.get("E2E_EXPECT_INFRA_LINKS", "false") == "true":
        assert "dashboard" in data, "Expected CloudWatch dashboard link"
        assert "lambda_logs" in data, "Expected Lambda log group link"
        assert data["dashboard"].startswith("https://")
        assert data["lambda_logs"].startswith("https://")
