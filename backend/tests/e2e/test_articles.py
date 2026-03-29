"""
Article E2E tests.

These tests add a real feed and wait briefly for the background fetch to complete,
then exercise article listing, read/unread, and keyword filtering.
"""

import time

import httpx
import pytest

# A stable, well-known feed that reliably has articles
TEST_FEED_URL = "https://feeds.bbci.co.uk/news/rss.xml"


@pytest.fixture(scope="module")
def feed_with_articles(base_url, auth_headers):
    """Add a feed and wait up to 15s for articles to appear."""
    resp = httpx.post(
        f"{base_url}/feeds",
        json={"url": TEST_FEED_URL},
        headers=auth_headers,
    )
    # Tolerate 409 if the feed already exists from a previous run
    if resp.status_code == 409:
        feeds = httpx.get(f"{base_url}/feeds", headers=auth_headers).json()
        feed = next(f for f in feeds if f["url"] == TEST_FEED_URL)
    else:
        assert resp.status_code == 201
        feed = resp.json()

    # Wait for background fetch
    for _ in range(15):
        articles = httpx.get(
            f"{base_url}/articles",
            params={"feed_id": feed["id"], "limit": 1},
            headers=auth_headers,
        ).json()
        if articles.get("items"):
            break
        time.sleep(1)

    yield feed

    # Cleanup
    httpx.delete(f"{base_url}/feeds/{feed['id']}", headers=auth_headers)


def test_list_articles(base_url, auth_headers, feed_with_articles):
    resp = httpx.get(
        f"{base_url}/articles",
        params={"feed_id": feed_with_articles["id"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "next_cursor" in data
    assert len(data["items"]) > 0


def test_article_pagination(base_url, auth_headers, feed_with_articles):
    resp = httpx.get(
        f"{base_url}/articles",
        params={"feed_id": feed_with_articles["id"], "limit": 2},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2


def test_mark_read_unread(base_url, auth_headers, feed_with_articles):
    articles = httpx.get(
        f"{base_url}/articles",
        params={"feed_id": feed_with_articles["id"], "limit": 1},
        headers=auth_headers,
    ).json()["items"]
    assert articles, "No articles available to test read/unread"

    article_id = articles[0]["id"]

    # Mark read
    resp = httpx.patch(f"{base_url}/articles/{article_id}/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True

    # Mark unread
    resp = httpx.patch(f"{base_url}/articles/{article_id}/unread", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is False


def test_unread_filter(base_url, auth_headers, feed_with_articles):
    # Get an article and mark it read
    articles = httpx.get(
        f"{base_url}/articles",
        params={"feed_id": feed_with_articles["id"], "limit": 1},
        headers=auth_headers,
    ).json()["items"]
    assert articles
    article_id = articles[0]["id"]

    httpx.patch(f"{base_url}/articles/{article_id}/read", headers=auth_headers)

    # Unread-only filter should not include it
    unread = httpx.get(
        f"{base_url}/articles",
        params={"feed_id": feed_with_articles["id"], "unread_only": "true", "limit": 100},
        headers=auth_headers,
    ).json()["items"]
    unread_ids = [a["id"] for a in unread]
    assert article_id not in unread_ids

    # Cleanup
    httpx.patch(f"{base_url}/articles/{article_id}/unread", headers=auth_headers)


def test_keyword_filter(base_url, auth_headers, feed_with_articles):
    resp = httpx.get(
        f"{base_url}/articles",
        params={"feed_id": feed_with_articles["id"], "keyword": "the"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # Just verifies the filter doesn't error; result count is environment-dependent


def test_articles_unauthenticated(base_url):
    resp = httpx.get(f"{base_url}/articles")
    assert resp.status_code in (401, 403)
