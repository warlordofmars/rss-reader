from datetime import datetime

import feedparser

from db import Article, Feed, SessionLocal


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6])
            except Exception:
                pass
    return datetime.utcnow()


def _get_content(entry) -> str:
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    return getattr(entry, "summary", "")


def fetch_feed(feed_id: int) -> None:
    db = SessionLocal()
    try:
        feed = db.query(Feed).filter(Feed.id == feed_id).first()
        if not feed:
            return

        parsed = feedparser.parse(feed.url)

        feed_title = parsed.feed.get("title", "")
        if feed_title and not feed.title:
            feed.title = feed_title
            db.commit()

        existing_guids = {a.guid for a in feed.articles}

        new_articles = []
        for entry in parsed.entries:
            guid = getattr(entry, "id", None) or getattr(entry, "link", "")
            if not guid or guid in existing_guids:
                continue
            new_articles.append(
                Article(
                    feed_id=feed.id,
                    guid=guid,
                    title=getattr(entry, "title", ""),
                    link=getattr(entry, "link", ""),
                    content=_get_content(entry),
                    summary=getattr(entry, "summary", ""),
                    published_at=_parse_date(entry),
                )
            )

        if new_articles:
            db.add_all(new_articles)
            db.commit()
    finally:
        db.close()


def fetch_all_feeds() -> None:
    db = SessionLocal()
    try:
        feed_ids = [row[0] for row in db.query(Feed.id).all()]
    finally:
        db.close()

    for feed_id in feed_ids:
        try:
            fetch_feed(feed_id)
        except Exception:
            pass
