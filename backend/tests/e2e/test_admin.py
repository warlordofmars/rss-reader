import httpx


def test_admin_users_requires_auth(base_url):
    resp = httpx.get(f"{base_url}/admin/users")
    assert resp.status_code == 401


def test_admin_users_wrong_password(base_url):
    resp = httpx.get(f"{base_url}/admin/users", auth=("admin", "wrong-password"))
    assert resp.status_code == 401


def test_admin_list_users(base_url, admin_auth, e2e_user):
    resp = httpx.get(f"{base_url}/admin/users", auth=admin_auth)
    assert resp.status_code == 200
    users = resp.json()
    assert isinstance(users, list)
    # Our e2e test user should appear
    emails = [u["email"] for u in users]
    assert e2e_user["email"] in emails


def test_admin_user_has_expected_fields(base_url, admin_auth):
    resp = httpx.get(f"{base_url}/admin/users", auth=admin_auth)
    assert resp.status_code == 200
    users = resp.json()
    assert users, "Expected at least one user"
    user = users[0]
    for field in ("google_id", "email", "name", "feed_count", "article_count", "total_unread"):
        assert field in user, f"Missing field: {field}"


def test_admin_get_user(base_url, admin_auth, e2e_user):
    resp = httpx.get(f"{base_url}/admin/users/{e2e_user['google_id']}", auth=admin_auth)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == e2e_user["email"]
    assert "feeds" in data


def test_admin_get_nonexistent_user(base_url, admin_auth):
    resp = httpx.get(f"{base_url}/admin/users/nonexistent-id", auth=admin_auth)
    assert resp.status_code == 404


def test_admin_infra(base_url, admin_auth):
    resp = httpx.get(f"{base_url}/admin/infra", auth=admin_auth)
    assert resp.status_code == 200
    # Links are optional (only present on Lambda), but if present must be valid URLs
    data = resp.json()
    for key in ("dashboard", "lambda_logs"):
        if key in data:
            assert data[key].startswith("https://"), f"{key} is not a valid URL"
