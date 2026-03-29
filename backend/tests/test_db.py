"""Tests for db helper functions and admin operations."""

from datetime import datetime


def test_list_all_users_empty(aws):
    import db as _db

    assert _db.list_all_users() == []


def test_list_all_users(aws):
    import db as _db

    _db.upsert_user("u1", "a@example.com", "A", "")
    _db.upsert_user("u2", "b@example.com", "B", "")

    users = _db.list_all_users()
    emails = {u["email"] for u in users}
    assert emails == {"a@example.com", "b@example.com"}


def test_get_user_feed_stats_no_feeds(aws, user):
    import db as _db

    stats = _db.get_user_feed_stats(user["google_id"])
    assert stats["feed_count"] == 0
    assert stats["total_unread"] == 0
    assert stats["feeds"] == []


def test_get_user_feed_stats_with_feeds(aws, user, feed):
    import db as _db

    stats = _db.get_user_feed_stats(user["google_id"])
    assert stats["feed_count"] == 1
    assert len(stats["feeds"]) == 1
    assert stats["feeds"][0]["feed_id"] == feed["id"]


def test_count_user_articles_zero(aws, user):
    import db as _db

    assert _db.count_user_articles(user["google_id"]) == 0


def test_count_user_articles(aws, user, feed):
    import db as _db

    _db.create_article(
        feed_id=feed["id"],
        user_id=user["google_id"],
        guid="guid-1",
        title="Article",
        link="https://example.com/1",
        content="content",
        summary="summary",
        published_at=datetime(2024, 1, 1),
    )
    assert _db.count_user_articles(user["google_id"]) == 1


def test_s3_content_overflow(aws, user, feed):
    """Articles with large content should be stored in S3 and retrieved transparently."""
    import db as _db

    # Content larger than the inline threshold
    big_content = "x" * 400_001

    _db.create_article(
        feed_id=feed["id"],
        user_id=user["google_id"],
        guid="guid-large",
        title="Large Article",
        link="https://example.com/large",
        content=big_content,
        summary="summary",
        published_at=datetime(2024, 1, 1),
    )

    # Retrieve and verify content came back from S3
    items, _ = _db.list_articles(
        user_id=user["google_id"],
        feed_id=feed["id"],
        limit=10,
        cursor=None,
        unread_only=False,
        keyword=None,
    )
    assert len(items) == 1
    article_id = items[0]["id"]
    feed_id_dec, sk = _db.decode_article_id(article_id)
    article = _db.get_article(feed_id_dec, sk)
    assert article["content"] == big_content


def test_from_ddb_nested_decimal(aws):
    """_from_ddb should handle nested dicts and lists with Decimal values."""
    from decimal import Decimal

    import db as _db

    raw = {
        "count": Decimal("5"),
        "nested": {"value": Decimal("3.14")},
        "list": [Decimal("1"), Decimal("2")],
    }
    result = _db._from_ddb(raw)
    assert result["count"] == 5
    assert isinstance(result["count"], int)
    assert isinstance(result["nested"]["value"], float)
    assert result["list"] == [1, 2]


def test_mark_article_read_wrong_user(aws, user, feed):
    """mark_article_read returns None if article belongs to a different user."""
    import db as _db

    _db.create_article(
        feed_id=feed["id"],
        user_id=user["google_id"],
        guid="guid-own",
        title="My Article",
        link="https://example.com",
        content="content",
        summary="",
        published_at=datetime(2024, 1, 1),
    )
    items, _ = _db.list_articles(
        user_id=user["google_id"],
        feed_id=feed["id"],
        limit=10,
        cursor=None,
        unread_only=False,
        keyword=None,
    )
    feed_id_dec, sk = _db.decode_article_id(items[0]["id"])

    result = _db.mark_article_read(feed_id_dec, sk, "wrong-user-id", is_read=True)
    assert result is None
