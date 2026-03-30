import httpx
import pytest


@pytest.fixture(autouse=True)
def cleanup_feeds(base_url, auth_headers):
    """Wipe all feeds before each test; track any created for post-test cleanup."""
    resp = httpx.get(f"{base_url}/feeds", headers=auth_headers)
    if resp.status_code == 200:
        for feed in resp.json():
            httpx.delete(f"{base_url}/feeds/{feed['id']}", headers=auth_headers)
    created = []
    yield created
    for feed_id in created:
        httpx.delete(f"{base_url}/feeds/{feed_id}", headers=auth_headers)


def test_list_feeds_returns_list(base_url, auth_headers):
    resp = httpx.get(f"{base_url}/feeds", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_add_and_delete_feed(base_url, auth_headers, cleanup_feeds):
    # Add
    resp = httpx.post(
        f"{base_url}/feeds",
        json={"url": "https://feeds.bbci.co.uk/news/rss.xml"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    feed = resp.json()
    assert feed["url"] == "https://feeds.bbci.co.uk/news/rss.xml"
    assert "id" in feed
    cleanup_feeds.append(feed["id"])

    # Appears in list
    resp = httpx.get(f"{base_url}/feeds", headers=auth_headers)
    ids = [f["id"] for f in resp.json()]
    assert feed["id"] in ids

    # Delete
    resp = httpx.delete(f"{base_url}/feeds/{feed['id']}", headers=auth_headers)
    assert resp.status_code == 204
    cleanup_feeds.remove(feed["id"])

    # Gone from list
    resp = httpx.get(f"{base_url}/feeds", headers=auth_headers)
    ids = [f["id"] for f in resp.json()]
    assert feed["id"] not in ids


def test_add_duplicate_feed(base_url, auth_headers, cleanup_feeds):
    resp = httpx.post(
        f"{base_url}/feeds",
        json={"url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    cleanup_feeds.append(resp.json()["id"])

    resp2 = httpx.post(
        f"{base_url}/feeds",
        json={"url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
        headers=auth_headers,
    )
    assert resp2.status_code == 409


def test_delete_nonexistent_feed(base_url, auth_headers):
    resp = httpx.delete(f"{base_url}/feeds/nonexistent-feed-id", headers=auth_headers)
    assert resp.status_code == 404


def test_refresh_feed(base_url, auth_headers, cleanup_feeds):
    resp = httpx.post(
        f"{base_url}/feeds",
        json={"url": "https://feeds.bbci.co.uk/news/technology/rss.xml"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    feed_id = resp.json()["id"]
    cleanup_feeds.append(feed_id)

    resp = httpx.post(f"{base_url}/feeds/{feed_id}/refresh", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "refreshing"
