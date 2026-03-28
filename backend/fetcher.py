from datetime import UTC, datetime

import feedparser

import db


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6])
            except Exception:  # noqa: S110
                pass
    return datetime.now(UTC).replace(tzinfo=None)


def _get_content(entry) -> str:
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    return getattr(entry, "summary", "")


def fetch_feed(feed: dict) -> None:
    """
    Fetch and store new articles for a single feed.

    `feed` is the raw dict returned by db.list_all_feeds() or db.get_feed_raw(),
    which includes feed_id, user_id, url, and title.
    """
    feed_id = feed["feed_id"]
    user_id = feed["user_id"]
    url = feed["url"]
    current_title = feed.get("title", "")

    parsed = feedparser.parse(url)

    feed_title = parsed.feed.get("title", "")
    if feed_title and not current_title:
        db.update_feed_title(user_id, feed_id, feed_title)

    for entry in parsed.entries:
        guid = getattr(entry, "id", None) or getattr(entry, "link", "")
        if not guid:
            continue
        if db.article_guid_exists(feed_id, guid):
            continue
        try:
            db.create_article(
                feed_id=feed_id,
                user_id=user_id,
                guid=guid,
                title=getattr(entry, "title", ""),
                link=getattr(entry, "link", ""),
                content=_get_content(entry),
                summary=getattr(entry, "summary", ""),
                published_at=_parse_date(entry),
            )
        except Exception:  # noqa: S110
            pass


def fetch_all_feeds() -> None:
    feeds = db.list_all_feeds()
    for feed in feeds:
        try:
            fetch_feed(feed)
        except Exception:  # noqa: S110
            pass
