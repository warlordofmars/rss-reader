from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from fetcher import _get_content, _parse_date, fetch_all_feeds, fetch_feed

# ── Unit tests for helper functions ──────────────────────────────────────────


def test_parse_date_from_published_parsed():
    entry = SimpleNamespace(published_parsed=(2024, 6, 15, 12, 0, 0, 0, 0, 0), updated_parsed=None)
    result = _parse_date(entry)
    assert result == datetime(2024, 6, 15, 12, 0, 0)


def test_parse_date_falls_back_to_updated_parsed():
    entry = SimpleNamespace(published_parsed=None, updated_parsed=(2024, 3, 1, 8, 30, 0, 0, 0, 0))
    result = _parse_date(entry)
    assert result == datetime(2024, 3, 1, 8, 30, 0)


def test_parse_date_falls_back_to_utcnow_when_missing():
    entry = SimpleNamespace(published_parsed=None, updated_parsed=None)
    before = datetime.now(UTC).replace(tzinfo=None)
    result = _parse_date(entry)
    after = datetime.now(UTC).replace(tzinfo=None)
    assert before <= result <= after


def test_parse_date_skips_invalid_tuple_and_tries_next():
    entry = SimpleNamespace(
        published_parsed=(2024, 13, 1, 0, 0, 0),  # invalid month
        updated_parsed=(2024, 3, 1, 8, 30, 0, 0, 0, 0),
    )
    result = _parse_date(entry)
    assert result == datetime(2024, 3, 1, 8, 30, 0)


def test_get_content_prefers_content_field():
    entry = SimpleNamespace(
        content=[{"value": "<p>Full content</p>"}],
        summary="Short summary",
    )
    assert _get_content(entry) == "<p>Full content</p>"


def test_get_content_falls_back_to_summary():
    entry = SimpleNamespace(summary="Just a summary")
    assert _get_content(entry) == "Just a summary"


def test_get_content_empty_content_list_falls_back():
    entry = SimpleNamespace(content=[], summary="Fallback")
    assert _get_content(entry) == "Fallback"


# ── Integration tests for fetch_feed ─────────────────────────────────────────


def _make_fake_parsed(title="Test Feed", entries=None):
    if entries is None:
        entries = [
            SimpleNamespace(
                id="entry-1",
                title="Article One",
                link="https://example.com/1",
                summary="Summary one",
                content=[{"value": "<p>Content one</p>"}],
                published_parsed=(2024, 1, 10, 0, 0, 0, 0, 0, 0),
                updated_parsed=None,
            )
        ]
    return SimpleNamespace(feed={"title": title}, entries=entries)


def _feed_dict(user_id, feed):
    """Build a feed dict as fetch_feed expects."""
    import db

    raw = db.get_feed_raw(user_id, feed["id"])
    return raw


def test_fetch_feed_creates_articles(aws, feed, user):
    import db

    fake_parsed = _make_fake_parsed()
    feed_dict = _feed_dict(user["google_id"], feed)

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        fetch_feed(feed_dict)

    items, _ = db.list_articles(
        user_id=user["google_id"], feed_id=feed["id"],
        limit=100, cursor=None, unread_only=False, keyword=None,
    )
    assert len(items) == 1
    assert items[0]["title"] == "Article One"


def test_fetch_feed_sets_feed_title(aws, feed, user):
    import db

    # Clear the title first
    db.update_feed_title(user["google_id"], feed["id"], "")
    feed_dict = _feed_dict(user["google_id"], feed)
    feed_dict["title"] = ""

    with patch("fetcher.feedparser.parse", return_value=_make_fake_parsed(title="My Blog")):
        fetch_feed(feed_dict)

    updated = db.get_feed(user["google_id"], feed["id"])
    assert updated["title"] == "My Blog"


def test_fetch_feed_skips_duplicate_guids(aws, feed, user):
    import db

    fake_parsed = _make_fake_parsed()
    feed_dict = _feed_dict(user["google_id"], feed)

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        fetch_feed(feed_dict)
        fetch_feed(feed_dict)  # second call — same entry

    items, _ = db.list_articles(
        user_id=user["google_id"], feed_id=feed["id"],
        limit=100, cursor=None, unread_only=False, keyword=None,
    )
    assert len(items) == 1


def test_fetch_feed_increments_unread_count(aws, feed, user):
    import db

    fake_parsed = _make_fake_parsed()
    feed_dict = _feed_dict(user["google_id"], feed)

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        fetch_feed(feed_dict)

    feeds = db.list_feeds(user["google_id"])
    assert feeds[0]["unread_count"] == 1


# ── fetch_all_feeds ───────────────────────────────────────────────────────────


def test_fetch_all_feeds_calls_fetch_feed_for_each(aws, user):
    import db

    f1 = db.create_feed(user["google_id"], "https://a.com/rss", title="A")
    f2 = db.create_feed(user["google_id"], "https://b.com/rss", title="B")

    with patch("fetcher.fetch_feed") as mock_fetch:
        fetch_all_feeds()

    called_urls = {call.args[0]["url"] for call in mock_fetch.call_args_list}
    assert called_urls == {f1["url"], f2["url"]}


def test_fetch_all_feeds_swallows_per_feed_exceptions(aws, user):
    import db

    db.create_feed(user["google_id"], "https://a.com/rss", title="A")
    db.create_feed(user["google_id"], "https://b.com/rss", title="B")

    call_count = 0

    def raise_on_first(feed):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("network error")

    with patch("fetcher.fetch_feed", side_effect=raise_on_first):
        fetch_all_feeds()  # should not raise


def test_fetch_feed_skips_entry_with_no_guid(aws, feed, user):
    """Entries with no id and no link should be silently skipped."""
    import db

    no_guid_entry = SimpleNamespace(
        id=None,
        link=None,
        title="No GUID Article",
        summary="",
        published_parsed=(2024, 1, 1, 0, 0, 0, 0, 0, 0),
        updated_parsed=None,
    )
    # Remove the attributes entirely so getattr falls back to None
    del no_guid_entry.id
    del no_guid_entry.link

    fake_parsed = _make_fake_parsed(entries=[no_guid_entry])
    feed_dict = _feed_dict(user["google_id"], feed)

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        fetch_feed(feed_dict)

    items, _ = db.list_articles(
        user_id=user["google_id"], feed_id=feed["id"],
        limit=100, cursor=None, unread_only=False, keyword=None,
    )
    assert len(items) == 0


def test_fetch_feed_swallows_create_article_exception(aws, feed, user):
    """If create_article raises, fetch_feed should skip that entry and continue."""
    import db

    entries = [
        SimpleNamespace(
            id="guid-ok",
            title="Good Article",
            link="https://example.com/good",
            summary="",
            content=[],
            published_parsed=(2024, 1, 2, 0, 0, 0, 0, 0, 0),
            updated_parsed=None,
        ),
    ]
    fake_parsed = _make_fake_parsed(entries=entries)
    feed_dict = _feed_dict(user["google_id"], feed)

    original_create = db.create_article
    call_count = 0

    def raise_once(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("db error")
        return original_create(*args, **kwargs)

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        with patch("fetcher.db.create_article", side_effect=raise_once):
            fetch_feed(feed_dict)  # should not raise — exception is swallowed per noqa: S110
