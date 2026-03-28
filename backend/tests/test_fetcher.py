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
    # month=13 causes datetime() to raise, should fall through to updated_parsed
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


# ── Integration test for fetch_feed ──────────────────────────────────────────

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
    # feedparser returns a dict-like object for .feed, so use a plain dict
    return SimpleNamespace(feed={"title": title}, entries=entries)


def test_fetch_feed_creates_articles(db, feed, patch_fetcher_session):
    fake_parsed = _make_fake_parsed()

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        fetch_feed(feed.id)

    from db import Article
    articles = db.query(Article).filter(Article.feed_id == feed.id).all()
    assert len(articles) == 1
    assert articles[0].title == "Article One"
    assert articles[0].guid == "entry-1"


def test_fetch_feed_sets_feed_title(db, feed, patch_fetcher_session):
    feed.title = ""
    db.commit()

    with patch("fetcher.feedparser.parse", return_value=_make_fake_parsed(title="My Blog")):
        fetch_feed(feed.id)

    db.refresh(feed)
    assert feed.title == "My Blog"


def test_fetch_feed_skips_duplicate_guids(db, feed, patch_fetcher_session):
    fake_parsed = _make_fake_parsed()

    with patch("fetcher.feedparser.parse", return_value=fake_parsed):
        fetch_feed(feed.id)
        fetch_feed(feed.id)  # second call — same entry

    from db import Article
    articles = db.query(Article).filter(Article.feed_id == feed.id).all()
    assert len(articles) == 1


def test_fetch_feed_ignores_missing_feed_id(patch_fetcher_session):
    # Should not raise even if the feed doesn't exist
    with patch("fetcher.feedparser.parse") as mock_parse:
        fetch_feed(99999)
        mock_parse.assert_not_called()


# ── fetch_all_feeds ───────────────────────────────────────────────────────────

def test_fetch_all_feeds_calls_fetch_feed_for_each(db, user, patch_fetcher_session):
    from db import Feed

    f1 = Feed(user_id=user.id, url="https://a.com/rss", title="A")
    f2 = Feed(user_id=user.id, url="https://b.com/rss", title="B")
    db.add_all([f1, f2])
    db.commit()
    db.refresh(f1)
    db.refresh(f2)

    with patch("fetcher.fetch_feed") as mock_fetch:
        fetch_all_feeds()

    called_ids = {call.args[0] for call in mock_fetch.call_args_list}
    assert called_ids == {f1.id, f2.id}


def test_fetch_all_feeds_swallows_per_feed_exceptions(db, user, patch_fetcher_session):
    from db import Feed

    f1 = Feed(user_id=user.id, url="https://a.com/rss", title="A")
    f2 = Feed(user_id=user.id, url="https://b.com/rss", title="B")
    db.add_all([f1, f2])
    db.commit()
    db.refresh(f1)
    db.refresh(f2)

    call_count = 0

    def raise_on_first(feed_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("network error")

    with patch("fetcher.fetch_feed", side_effect=raise_on_first):
        fetch_all_feeds()  # should not raise

    assert call_count == 2  # both feeds were attempted
