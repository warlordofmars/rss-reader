"""Tests for admin routes and require_admin dependency."""

import base64


def _basic_auth(username, password):
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def test_admin_users_no_auth(client):
    resp = client.get("/admin/users")
    assert resp.status_code == 401


def test_admin_users_wrong_password(client):
    resp = client.get("/admin/users", headers=_basic_auth("admin", "wrong"))
    assert resp.status_code == 401


def test_admin_users_wrong_username(client):
    resp = client.get("/admin/users", headers=_basic_auth("notadmin", "admin"))
    assert resp.status_code == 401


def test_admin_list_users_empty(client):
    resp = client.get("/admin/users", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_admin_list_users(client, aws, user):
    resp = client.get("/admin/users", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    u = users[0]
    assert u["email"] == user["email"]
    assert u["google_id"] == user["google_id"]
    assert "feed_count" in u
    assert "article_count" in u
    assert "total_unread" in u
    assert "feeds" in u


def test_admin_list_users_sorted_by_created_at(client, aws):
    import db as _db

    _db.upsert_user("user-a", "a@example.com", "A", "")
    _db.upsert_user("user-b", "b@example.com", "B", "")

    resp = client.get("/admin/users", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 200
    users = resp.json()
    # Should be sorted newest first
    dates = [u["created_at"] for u in users if u.get("created_at")]
    assert dates == sorted(dates, reverse=True)


def test_admin_get_user(client, aws, user):
    resp = client.get(
        f"/admin/users/{user['google_id']}",
        headers=_basic_auth("admin", "admin"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == user["email"]
    assert "feeds" in data
    assert "feed_count" in data


def test_admin_get_user_not_found(client):
    resp = client.get("/admin/users/nonexistent", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 404


def test_admin_infra_no_env_vars(client):
    resp = client.get("/admin/infra", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 200
    # No env vars set — should return empty dict
    assert resp.json() == {}


def test_admin_infra_with_dashboard(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_NAME", "MyDashboard")
    monkeypatch.setenv("AWS_REGION", "us-west-2")

    resp = client.get("/admin/infra", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert "dashboard" in data
    assert "MyDashboard" in data["dashboard"]
    assert "us-west-2" in data["dashboard"]


def test_admin_infra_with_lambda(client, monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "my-function")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")

    resp = client.get("/admin/infra", headers=_basic_auth("admin", "admin"))
    assert resp.status_code == 200
    data = resp.json()
    assert "lambda_logs" in data
    assert "my-function" in data["lambda_logs"]
    assert "eu-west-1" in data["lambda_logs"]


def test_admin_users_includes_feed_stats(client, aws, user):
    import db as _db

    _db.create_feed(user["google_id"], "https://example.com/feed.xml", title="Test Feed")

    resp = client.get("/admin/users", headers=_basic_auth("admin", "admin"))
    u = resp.json()[0]
    assert u["feed_count"] == 1
    assert len(u["feeds"]) == 1
    assert u["feeds"][0]["title"] == "Test Feed"
