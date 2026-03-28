from datetime import datetime


def _make_article(feed_id, user_id, title="Test Article", is_read=False, published_at=None):
    import db

    db.create_article(
        feed_id=feed_id,
        user_id=user_id,
        guid=f"guid-{title}",
        title=title,
        link="https://example.com/article",
        content="<p>Content</p>",
        summary="Summary",
        published_at=published_at or datetime(2024, 1, 1),
    )
    if is_read:
        # Mark it read directly so unread_count stays consistent
        items, _ = db.list_articles(
            user_id=user_id, feed_id=feed_id, limit=100, cursor=None,
            unread_only=False, keyword=None,
        )
        for a in items:
            if a["title"] == title:
                feed_id_a, sk = db.decode_article_id(a["id"])
                db.mark_article_read(feed_id_a, sk, user_id, is_read=True)
                break


def test_list_articles_empty(client, auth_headers):
    resp = client.get("/articles", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["next_cursor"] is None


def test_list_articles(client, auth_headers, aws, feed, user):
    _make_article(feed["id"], user["google_id"], "Article One")
    _make_article(feed["id"], user["google_id"], "Article Two")

    resp = client.get("/articles", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_list_articles_by_feed(client, auth_headers, aws, feed, user):
    import db

    other_feed = db.create_feed(user["google_id"], "https://other.com/rss", title="Other")

    _make_article(feed["id"], user["google_id"], "In Feed")
    _make_article(other_feed["id"], user["google_id"], "In Other Feed")

    resp = client.get(f"/articles?feed_id={feed['id']}", headers=auth_headers)
    data = resp.json()["items"]
    assert len(data) == 1
    assert data[0]["title"] == "In Feed"


def test_list_articles_forbidden_feed(client, auth_headers, aws):
    resp = client.get("/articles?feed_id=not-my-feed", headers=auth_headers)
    assert resp.status_code == 403


def test_list_articles_keyword_filter(client, auth_headers, aws, feed, user):
    _make_article(feed["id"], user["google_id"], "Python Tutorial")
    _make_article(feed["id"], user["google_id"], "JavaScript Guide")

    resp = client.get("/articles?keyword=Python", headers=auth_headers)
    data = resp.json()["items"]
    assert len(data) == 1
    assert data[0]["title"] == "Python Tutorial"


def test_list_articles_unread_only(client, auth_headers, aws, feed, user):
    _make_article(feed["id"], user["google_id"], "Unread Article", is_read=False)
    _make_article(feed["id"], user["google_id"], "Read Article", is_read=True)

    resp = client.get("/articles?unread_only=true", headers=auth_headers)
    data = resp.json()["items"]
    assert len(data) == 1
    assert data[0]["title"] == "Unread Article"


def test_list_articles_pagination(client, auth_headers, aws, feed, user):
    from datetime import timedelta

    base = datetime(2024, 1, 1)
    for i in range(5):
        _make_article(
            feed["id"], user["google_id"],
            title=f"Article {i}",
            published_at=base + timedelta(days=i),
        )

    # Page 1: 3 items
    resp = client.get("/articles?limit=3", headers=auth_headers)
    body = resp.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is not None

    # Page 2: remaining 2 items
    resp2 = client.get(f"/articles?limit=3&cursor={body['next_cursor']}", headers=auth_headers)
    body2 = resp2.json()
    assert len(body2["items"]) == 2
    assert body2["next_cursor"] is None

    # No duplicates across pages
    ids_p1 = {a["id"] for a in body["items"]}
    ids_p2 = {a["id"] for a in body2["items"]}
    assert ids_p1.isdisjoint(ids_p2)


def test_mark_read(client, auth_headers, aws, feed, user):
    _make_article(feed["id"], user["google_id"], is_read=False)

    resp = client.get("/articles", headers=auth_headers)
    article = resp.json()["items"][0]

    resp = client.patch(f"/articles/{article['id']}/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


def test_mark_unread(client, auth_headers, aws, feed, user):
    _make_article(feed["id"], user["google_id"], is_read=True)

    resp = client.get("/articles", headers=auth_headers)
    article = resp.json()["items"][0]

    resp = client.patch(f"/articles/{article['id']}/unread", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is False


def test_cannot_access_other_users_article(client, aws, feed, user):
    import db
    from main import create_jwt

    _make_article(feed["id"], user["google_id"])

    resp_articles = client.get(
        "/articles",
        headers={"Authorization": f"Bearer {create_jwt(user['google_id'], user['email'])}"},
    )
    article = resp_articles.json()["items"][0]

    other = db.upsert_user("evil-789", "evil@example.com", "Evil", "")
    evil_headers = {"Authorization": f"Bearer {create_jwt(other['google_id'], other['email'])}"}

    resp = client.patch(f"/articles/{article['id']}/read", headers=evil_headers)
    assert resp.status_code == 404
