from unittest.mock import patch


def test_list_feeds_empty(client, auth_headers):
    resp = client.get("/feeds", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_feeds_returns_feed(client, auth_headers, feed):
    resp = client.get("/feeds", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["url"] == feed["url"]
    assert data[0]["title"] == feed["title"]
    assert "unread_count" in data[0]


def test_add_feed(client, auth_headers):
    with patch("main.threading.Thread"):
        resp = client.post(
            "/feeds",
            json={"url": "https://news.example.com/rss"},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["url"] == "https://news.example.com/rss"


def test_add_feed_duplicate(client, auth_headers, feed):
    with patch("main.threading.Thread"):
        resp = client.post(
            "/feeds",
            json={"url": feed["url"]},
            headers=auth_headers,
        )
    assert resp.status_code == 409


def test_delete_feed(client, auth_headers, feed):
    resp = client.delete(f"/feeds/{feed['id']}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get("/feeds", headers=auth_headers)
    assert resp.json() == []


def test_delete_feed_not_found(client, auth_headers):
    resp = client.delete("/feeds/nonexistent-feed-id", headers=auth_headers)
    assert resp.status_code == 404


def test_delete_feed_wrong_user(client, aws, feed):
    import db
    from main import create_jwt

    other = db.upsert_user("other-456", "other@example.com", "Other", "")
    headers = {"Authorization": f"Bearer {create_jwt(other['google_id'], other['email'])}"}

    resp = client.delete(f"/feeds/{feed['id']}", headers=headers)
    assert resp.status_code == 404


def test_requires_auth(client):
    resp = client.get("/feeds")
    assert resp.status_code == 401


def test_refresh_feed(client, auth_headers, feed):
    with patch("main.threading.Thread"):
        resp = client.post(f"/feeds/{feed['id']}/refresh", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "refreshing"
