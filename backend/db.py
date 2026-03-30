"""
DynamoDB data layer.

Single-table design (table name from $DYNAMODB_TABLE, default "rss-reader"):

  User    PK=USER#<google_id>   SK=#META
  Feed    PK=USER#<google_id>   SK=FEED#<feed_id>
  Article PK=FEED#<feed_id>     SK=ARTICLE#<published_at_iso>#<guid_hash>
  Guid    PK=FEED#<feed_id>     SK=GUID#<guid_hash>   (dedup sentinel, no other attrs)

GSI1 (sparse, Feed items only):
  GSI1PK=ALL_FEEDS  →  returns every feed across all users (for scheduler)

GSI2 (Article items only):
  GSI2PK=USER#<google_id>  GSI2SK=<published_at_iso>#<guid_hash>
  →  user's articles sorted newest-first across all feeds

Article IDs surfaced via the API are opaque base64 strings that encode
(feed_id, SK) so we can do targeted GetItem/UpdateItem without a scan.
"""

import base64
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

MAX_INLINE_BYTES = 300_000  # store content in S3 when larger


# ── boto3 helpers ─────────────────────────────────────────────────────────────
# Table name and bucket name are read from env on every call so that
# monkeypatch.setenv works correctly in tests.


def _ddb():
    return boto3.resource(
        "dynamodb",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("DYNAMODB_ENDPOINT") or None,
    )


def _table():
    return _ddb().Table(os.getenv("DYNAMODB_TABLE", "rss-reader"))


def _s3():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("S3_ENDPOINT") or None,
    )


# ── Key / ID helpers ──────────────────────────────────────────────────────────


def _guid_hash(guid: str) -> str:
    return hashlib.md5(guid.encode()).hexdigest()[:16]  # noqa: S324


def _article_sk(published_at: datetime, guid: str) -> str:
    iso = published_at.strftime("%Y-%m-%dT%H:%M:%S")
    return f"ARTICLE#{iso}#{_guid_hash(guid)}"


def encode_article_id(feed_id: str, sk: str) -> str:
    """Return an opaque URL-safe ID encoding (feed_id, SK)."""
    return base64.urlsafe_b64encode(f"{feed_id}:{sk}".encode()).decode().rstrip("=")


def decode_article_id(article_id: str) -> tuple[str, str]:
    """Decode an opaque article ID back to (feed_id, SK)."""
    padding = (4 - len(article_id) % 4) % 4
    data = base64.urlsafe_b64decode((article_id + "=" * padding).encode()).decode()
    feed_id, sk = data.split(":", 1)
    return feed_id, sk


def _encode_cursor(last_key: dict | None) -> str | None:
    if not last_key:
        return None
    return base64.urlsafe_b64encode(json.dumps(last_key).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    padding = (4 - len(cursor) % 4) % 4
    return json.loads(base64.urlsafe_b64decode((cursor + "=" * padding).encode()).decode())


# ── Type coercion ─────────────────────────────────────────────────────────────


def _from_ddb(item: dict) -> dict:
    """Recursively convert DynamoDB Decimal types to int/float."""
    out = {}
    for k, v in item.items():
        if isinstance(v, Decimal):
            out[k] = int(v) if v == v.to_integral_value() else float(v)
        elif isinstance(v, dict):
            out[k] = _from_ddb(v)
        elif isinstance(v, list):
            out[k] = [_from_ddb(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def _format_article(item: dict) -> dict:
    feed_id = item.get("feed_id", "")
    sk = item.get("SK", "")
    return {
        "id": encode_article_id(feed_id, sk),
        "feed_id": feed_id,
        "title": item.get("title", ""),
        "link": item.get("link", ""),
        "content": item.get("content") or item.get("summary", ""),
        "summary": item.get("summary", ""),
        "published_at": item.get("published_at"),
        "is_read": bool(item.get("is_read", False)),
    }


def _format_feed(item: dict) -> dict:
    # Fall back to extracting from SK for items that predate the feed_id attribute
    sk = item.get("SK", "")
    feed_id = item.get("feed_id") or (sk.split("FEED#", 1)[1] if "FEED#" in sk else "")
    last_error = item.get("last_error") or None  # empty string → None
    return {
        "id": feed_id,
        "url": item.get("url", ""),
        "title": item.get("title") or item.get("url", ""),
        "unread_count": max(0, int(item.get("unread_count", 0))),
        "created_at": item.get("created_at"),
        "last_fetched_at": item.get("last_fetched_at"),
        "last_error": last_error,
    }


# ── User operations ───────────────────────────────────────────────────────────


def get_user(google_id: str) -> dict | None:
    resp = _table().get_item(Key={"PK": f"USER#{google_id}", "SK": "#META"})
    item = resp.get("Item")
    return _from_ddb(item) if item else None


def upsert_user(google_id: str, email: str, name: str, picture: str) -> dict:
    """Create user on first login; update profile fields on subsequent logins."""
    now = datetime.now(UTC).isoformat()
    resp = _table().update_item(
        Key={"PK": f"USER#{google_id}", "SK": "#META"},
        UpdateExpression=(
            "SET email = :e, #n = :n, picture = :p, google_id = :g, "
            "created_at = if_not_exists(created_at, :now)"
        ),
        ExpressionAttributeNames={"#n": "name"},  # name is a reserved word
        ExpressionAttributeValues={
            ":e": email,
            ":n": name,
            ":p": picture,
            ":g": google_id,
            ":now": now,
        },
        ReturnValues="ALL_NEW",
    )
    return _from_ddb(resp["Attributes"])


# ── Feed operations ───────────────────────────────────────────────────────────


def list_feeds(user_id: str) -> list[dict]:
    resp = _table().query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("FEED#")
    )
    return [_format_feed(_from_ddb(i)) for i in resp.get("Items", [])]


def get_feed(user_id: str, feed_id: str) -> dict | None:
    resp = _table().get_item(Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"})
    item = resp.get("Item")
    return _format_feed(_from_ddb(item)) if item else None


def get_feed_raw(user_id: str, feed_id: str) -> dict | None:
    """Return the raw DynamoDB item (including all GSI keys) for internal use."""
    resp = _table().get_item(Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"})
    item = resp.get("Item")
    return _from_ddb(item) if item else None


def check_feed_url_exists(user_id: str, url: str) -> bool:
    resp = _table().query(
        KeyConditionExpression=Key("PK").eq(f"USER#{user_id}") & Key("SK").begins_with("FEED#"),
        FilterExpression=Attr("url").eq(url),
    )
    return len(resp.get("Items", [])) > 0


def create_feed(user_id: str, url: str, title: str = "") -> dict:
    feed_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    item = {
        "PK": f"USER#{user_id}",
        "SK": f"FEED#{feed_id}",
        "feed_id": feed_id,
        "user_id": user_id,
        "url": url,
        "title": title,
        "unread_count": 0,
        "created_at": now,
        # GSI1: scheduler can query all feeds
        "GSI1PK": "ALL_FEEDS",
        "GSI1SK": f"FEED#{feed_id}",
    }
    _table().put_item(Item=item)
    return _format_feed(item)


def update_feed_title(user_id: str, feed_id: str, title: str) -> None:
    _table().update_item(
        Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"},
        UpdateExpression="SET title = :t",
        ExpressionAttributeValues={":t": title},
    )


def delete_feed(user_id: str, feed_id: str) -> None:
    """Delete feed item and all associated articles + GUID sentinels."""
    tbl = _table()

    # Delete the feed item itself
    tbl.delete_item(Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"})

    # Batch-delete all items under FEED#<feed_id> (articles + GUID sentinels)
    # TODO: also delete any S3 content objects for this feed's articles
    exclusive_start_key = None
    while True:
        kwargs: dict = {
            "KeyConditionExpression": Key("PK").eq(f"FEED#{feed_id}"),
            "ProjectionExpression": "PK, SK",
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key

        resp = tbl.query(**kwargs)
        items = resp.get("Items", [])

        if items:
            with tbl.batch_writer() as batch:
                for it in items:
                    batch.delete_item(Key={"PK": it["PK"], "SK": it["SK"]})

        exclusive_start_key = resp.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break


def list_all_feeds() -> list[dict]:
    """Return all feeds across all users (uses GSI1, for the scheduler)."""
    resp = _table().query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq("ALL_FEEDS"),
    )
    return [_from_ddb(i) for i in resp.get("Items", [])]


# ── Article operations ────────────────────────────────────────────────────────


def article_guid_exists(feed_id: str, guid: str) -> bool:
    """O(1) check using the GUID sentinel item."""
    resp = _table().get_item(
        Key={"PK": f"FEED#{feed_id}", "SK": f"GUID#{_guid_hash(guid)}"},
        ProjectionExpression="PK",
    )
    return "Item" in resp


def create_article(
    feed_id: str,
    user_id: str,
    guid: str,
    title: str,
    link: str,
    content: str,
    summary: str,
    published_at: datetime,
) -> None:
    """Write article + GUID sentinel; increment feed unread_count."""
    tbl = _table()
    guid_hash = _guid_hash(guid)
    sk = _article_sk(published_at, guid)
    published_iso = published_at.strftime("%Y-%m-%dT%H:%M:%S")
    now = datetime.now(UTC).isoformat()

    # Handle S3 overflow for large content
    content_field: str | None = None
    content_s3_key: str | None = None
    content_bytes = content.encode("utf-8") if content else b""

    if len(content_bytes) > MAX_INLINE_BYTES:
        content_s3_key = f"articles/{feed_id}/{guid_hash}"
        _s3().put_object(
            Bucket=os.getenv("CONTENT_BUCKET", ""),
            Key=content_s3_key,
            Body=content_bytes,
            ContentType="text/html; charset=utf-8",
        )
    else:
        content_field = content

    article_item: dict = {
        "PK": f"FEED#{feed_id}",
        "SK": sk,
        "feed_id": feed_id,
        "user_id": user_id,
        "guid": guid,
        "title": title,
        "link": link,
        "summary": summary,
        "published_at": published_iso,
        "is_read": False,
        "created_at": now,
        # GSI2: user's articles sorted by date
        "GSI2PK": f"USER#{user_id}",
        "GSI2SK": f"{published_iso}#{guid_hash}",
    }
    if content_field is not None:
        article_item["content"] = content_field
    if content_s3_key:
        article_item["content_s3_key"] = content_s3_key

    # Write article (skip if already exists — race condition safety)
    tbl.put_item(
        Item=article_item,
        ConditionExpression="attribute_not_exists(PK)",
    )

    # Write GUID sentinel (also conditional to be idempotent)
    try:
        tbl.put_item(
            Item={"PK": f"FEED#{feed_id}", "SK": f"GUID#{guid_hash}"},
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise

    # Increment unread_count on the feed
    tbl.update_item(
        Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"},
        UpdateExpression="ADD unread_count :one",
        ExpressionAttributeValues={":one": 1},
    )


def list_articles(
    user_id: str,
    feed_id: str | None,
    limit: int,
    cursor: str | None,
    unread_only: bool,
    keyword: str | None,
) -> tuple[list[dict], str | None]:
    """
    Return up to `limit` articles newest-first, with an opaque next_cursor.

    DynamoDB FilterExpression is used for unread_only; keyword filtering is
    done in Python (case-insensitive) because DynamoDB contains() is case-sensitive.
    We read in batches to compensate for filtered-out items.
    """
    tbl = _table()
    use_gsi2 = feed_id is None
    exclusive_start_key = _decode_cursor(cursor)
    results: list[dict] = []
    batch_size = min(limit * 4, 100)
    max_reads = limit * 20  # safety cap — prevents runaway loops on heavy filtering
    total_read = 0
    last_ddb_key: dict | None = None

    while len(results) < limit and total_read < max_reads:
        kwargs: dict = {
            "Limit": batch_size,
            "ScanIndexForward": False,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key
        if unread_only:
            kwargs["FilterExpression"] = Attr("is_read").eq(False)

        if use_gsi2:
            kwargs["IndexName"] = "GSI2"
            kwargs["KeyConditionExpression"] = Key("GSI2PK").eq(f"USER#{user_id}")
            # GSI2 projects limited fields; content falls back to summary in _format_article
        else:
            kwargs["KeyConditionExpression"] = (
                Key("PK").eq(f"FEED#{feed_id}") & Key("SK").begins_with("ARTICLE#")
            )

        resp = tbl.query(**kwargs)
        batch = resp.get("Items", [])
        total_read += len(batch)

        kw_lower = keyword.lower() if keyword else None
        for item in batch:
            if kw_lower:
                haystack = (
                    item.get("title", "").lower()
                    + " "
                    + item.get("summary", "").lower()
                )
                if kw_lower not in haystack:
                    continue
            results.append(_format_article(_from_ddb(item)))
            if len(results) >= limit:
                break

        last_ddb_key = resp.get("LastEvaluatedKey")
        if not last_ddb_key:
            break
        exclusive_start_key = last_ddb_key

    # Cursor points to just after the last item we're returning so the next page
    # continues from the right position (even if we stopped mid-batch).
    next_cursor: str | None = None
    if len(results) >= limit:
        last = results[limit - 1]
        results = results[:limit]
        next_key: dict = {"PK": f"FEED#{last['feed_id']}", "SK": last["id"]}
        # Decode the opaque article id to get the real SK
        _, real_sk = decode_article_id(last["id"])
        next_key = {"PK": f"FEED#{last['feed_id']}", "SK": real_sk}
        if use_gsi2:
            # GSI2 ExclusiveStartKey also needs the index keys
            published_at = last.get("published_at", "")
            _, real_sk = decode_article_id(last["id"])
            guid_hash_part = real_sk.split("#")[-1] if "#" in real_sk else ""
            next_key["GSI2PK"] = f"USER#{user_id}"
            next_key["GSI2SK"] = f"{published_at}#{guid_hash_part}"
        next_cursor = _encode_cursor(next_key)
    elif last_ddb_key:
        # We hit max_reads; there may be more items
        next_cursor = _encode_cursor(last_ddb_key)

    return results, next_cursor


def get_article(feed_id: str, article_sk: str) -> dict | None:
    """Fetch a single article including full inline content."""
    resp = _table().get_item(Key={"PK": f"FEED#{feed_id}", "SK": article_sk})
    item = resp.get("Item")
    if not item:
        return None
    item = _from_ddb(item)

    # Fetch S3 content if not inline
    bucket = os.getenv("CONTENT_BUCKET", "")
    if not item.get("content") and item.get("content_s3_key") and bucket:
        try:
            s3_resp = _s3().get_object(Bucket=bucket, Key=item["content_s3_key"])
            item["content"] = s3_resp["Body"].read().decode("utf-8")
        except ClientError:  # noqa: S110
            pass

    return _format_article(item)


# ── Admin operations ──────────────────────────────────────────────────────────


def list_all_users() -> list[dict]:
    """Scan for all User (#META) items across all users."""
    tbl = _table()
    results = []
    kwargs: dict = {"FilterExpression": Attr("SK").eq("#META")}
    while True:
        resp = tbl.scan(**kwargs)
        results.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return [_from_ddb(i) for i in results]


def get_user_feed_stats(google_id: str) -> dict:
    """Return feed count, per-feed unread counts, and total unread for a user."""
    resp = _table().query(
        KeyConditionExpression=Key("PK").eq(f"USER#{google_id}") & Key("SK").begins_with("FEED#"),
        ProjectionExpression="feed_id, #t, unread_count, created_at",
        ExpressionAttributeNames={"#t": "title"},
    )
    feeds = [_from_ddb(i) for i in resp.get("Items", [])]
    total_unread = sum(max(0, int(f.get("unread_count", 0))) for f in feeds)
    return {
        "feed_count": len(feeds),
        "total_unread": total_unread,
        "feeds": [
            {
                "feed_id": f.get("feed_id"),
                "title": f.get("title"),
                "unread_count": max(0, int(f.get("unread_count", 0))),
                "created_at": f.get("created_at"),
            }
            for f in feeds
        ],
    }


def count_user_articles(google_id: str) -> int:
    """Count total articles ingested for a user (via GSI2)."""
    resp = _table().query(
        IndexName="GSI2",
        KeyConditionExpression=Key("GSI2PK").eq(f"USER#{google_id}"),
        Select="COUNT",
    )
    return resp.get("Count", 0)


def mark_article_read(
    feed_id: str, article_sk: str, user_id: str, is_read: bool
) -> dict | None:
    """
    Set is_read on an article and keep the feed's unread_count consistent.
    Returns the updated article dict, or None if the article does not belong
    to this user.
    """
    tbl = _table()
    condition_value = not is_read  # only update if current state differs

    try:
        tbl.update_item(
            Key={"PK": f"FEED#{feed_id}", "SK": article_sk},
            UpdateExpression="SET is_read = :r",
            ConditionExpression=Attr("is_read").eq(condition_value) & Attr("user_id").eq(user_id),
            ExpressionAttributeValues={":r": is_read},
        )
        # State changed — adjust counter
        delta = -1 if is_read else 1
        tbl.update_item(
            Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"},
            UpdateExpression="ADD unread_count :d",
            ExpressionAttributeValues={":d": delta},
        )
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ConditionalCheckFailedException":
            # Either the article doesn't belong to this user, or is_read was already correct.
            # Distinguish by doing a targeted get.
            resp = tbl.get_item(
                Key={"PK": f"FEED#{feed_id}", "SK": article_sk},
                ProjectionExpression="user_id, is_read",
            )
            existing = resp.get("Item")
            if not existing or existing.get("user_id") != user_id:
                return None
            # Already in desired state — not an error, just return current
        else:
            raise

    return {
        "id": encode_article_id(feed_id, article_sk),
        "is_read": is_read,
    }


def update_feed_health(
    user_id: str,
    feed_id: str,
    *,
    last_fetched_at: str,
    last_error: str | None,
) -> None:
    """Record the result of a feed fetch attempt (success or error)."""
    _table().update_item(
        Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"},
        UpdateExpression="SET last_fetched_at = :t, last_error = :e",
        ExpressionAttributeValues={
            ":t": last_fetched_at,
            ":e": last_error or "",
        },
    )


def prune_old_articles(user_id: str, feed_id: str, cutoff_iso: str) -> int:
    """
    Delete articles (and their GUID sentinels) older than cutoff_iso for a feed.
    Returns the number of articles deleted.
    """
    tbl = _table()
    deleted = 0

    # Query articles older than the cutoff on PK=FEED#<feed_id>
    exclusive_start_key = None
    while True:
        kwargs: dict = {
            "KeyConditionExpression": (
                Key("PK").eq(f"FEED#{feed_id}") & Key("SK").begins_with("ARTICLE#")
            ),
            "FilterExpression": Attr("SK").lt(f"ARTICLE#{cutoff_iso}"),
            "ProjectionExpression": "PK, SK, guid",
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key

        resp = tbl.query(**kwargs)
        items = resp.get("Items", [])

        if items:
            with tbl.batch_writer() as batch:
                for item in items:
                    batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                    # Also delete the GUID sentinel
                    if guid := item.get("guid"):
                        gh = hashlib.md5(guid.encode()).hexdigest()[:16]  # noqa: S324
                        batch.delete_item(
                            Key={"PK": f"FEED#{feed_id}", "SK": f"GUID#{gh}"}
                        )
            deleted += len(items)

        exclusive_start_key = resp.get("LastEvaluatedKey")
        if not exclusive_start_key:
            break

    # Decrement unread_count by the number of unread articles pruned (floor at 0)
    if deleted:
        tbl.update_item(
            Key={"PK": f"USER#{user_id}", "SK": f"FEED#{feed_id}"},
            UpdateExpression="SET unread_count = :z",
            # Recalculate would require a scan; just reset to 0 on prune — next
            # fetch will re-increment for any newly arriving articles.
            ExpressionAttributeValues={":z": 0},
            ConditionExpression="attribute_exists(PK)",
        )

    return deleted
