from datetime import datetime

from db import Article


def _make_article(db, feed_id, title="Test Article", is_read=False, published_at=None):
    a = Article(
        feed_id=feed_id,
        guid=f"guid-{title}",
        title=title,
        link="https://example.com/article",
        content="<p>Content</p>",
        summary="Summary",
        published_at=published_at or datetime(2024, 1, 1),
        is_read=is_read,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_list_articles_empty(client, auth_headers):
    resp = client.get("/articles", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_articles(client, auth_headers, db, feed):
    _make_article(db, feed.id, "Article One")
    _make_article(db, feed.id, "Article Two")

    resp = client.get("/articles", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_articles_by_feed(client, auth_headers, db, feed, user):
    from db import Feed

    other_feed = Feed(user_id=user.id, url="https://other.com/rss", title="Other")
    db.add(other_feed)
    db.commit()
    db.refresh(other_feed)

    _make_article(db, feed.id, "In Feed")
    _make_article(db, other_feed.id, "In Other Feed")

    resp = client.get(f"/articles?feed_id={feed.id}", headers=auth_headers)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "In Feed"


def test_list_articles_keyword_filter(client, auth_headers, db, feed):
    _make_article(db, feed.id, "Python Tutorial")
    _make_article(db, feed.id, "JavaScript Guide")

    resp = client.get("/articles?keyword=Python", headers=auth_headers)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Python Tutorial"


def test_list_articles_unread_only(client, auth_headers, db, feed):
    _make_article(db, feed.id, "Read Article", is_read=True)
    _make_article(db, feed.id, "Unread Article", is_read=False)

    resp = client.get("/articles?unread_only=true", headers=auth_headers)
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Unread Article"


def test_mark_read(client, auth_headers, db, feed):
    article = _make_article(db, feed.id, is_read=False)

    resp = client.patch(f"/articles/{article.id}/read", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True

    db.refresh(article)
    assert article.is_read is True


def test_mark_unread(client, auth_headers, db, feed):
    article = _make_article(db, feed.id, is_read=True)

    resp = client.patch(f"/articles/{article.id}/unread", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_read"] is False

    db.refresh(article)
    assert article.is_read is False


def test_cannot_access_other_users_article(client, db, feed):
    from db import User
    from main import create_jwt

    other = User(google_id="evil-789", email="evil@example.com", name="Evil", picture="")
    db.add(other)
    db.commit()
    db.refresh(other)
    headers = {"Authorization": f"Bearer {create_jwt(other.id, other.email)}"}

    article = _make_article(db, feed.id)
    resp = client.patch(f"/articles/{article.id}/read", headers=headers)
    assert resp.status_code == 404
