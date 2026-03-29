# Backend

FastAPI application serving the RSS Reader API. Runs on AWS Lambda via [Mangum](https://mangum.io), and locally via uvicorn.

## Local dev

```bash
uv sync
uv run uvicorn main:app --reload
```

API available at `http://localhost:8000`. Requires a populated `.env` file (see below).

Or from the repo root:

```bash
uv run inv dev
```

## Environment variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `JWT_SECRET` | Secret key for signing JWTs (long random string) |
| `REDIRECT_URI` | OAuth callback URL (default: `http://localhost:8000/auth/callback`) |
| `FRONTEND_URL` | Frontend origin for CORS (default: `http://localhost:5173`) |
| `DYNAMODB_TABLE` | DynamoDB table name — get from `uv run inv outputs` |
| `CONTENT_BUCKET` | S3 bucket for article content overflow — get from `uv run inv outputs` |
| `AWS_REGION` | AWS region (default: `us-east-1`) |

In Lambda, `DYNAMODB_TABLE`, `CONTENT_BUCKET`, and `APP_SECRET_ARN` are injected by CDK. The OAuth secrets and JWT secret are loaded from Secrets Manager at cold start by `handler.py`.

## Testing

```bash
uv run pytest -v
```

Tests use [moto](https://docs.getmoto.org) to mock DynamoDB and S3 in-process — no AWS credentials or running services needed.

## Layout

| File | Purpose |
| --- | --- |
| `main.py` | FastAPI app, route definitions, Google OAuth flow, JWT auth |
| `db.py` | DynamoDB single-table data layer (boto3) |
| `fetcher.py` | RSS feed fetching and article ingestion via feedparser |
| `handler.py` | Lambda entry point — loads Secrets Manager, wraps app with Mangum |
| `scheduler.py` | APScheduler job (local dev only — EventBridge handles scheduling in Lambda) |

## DynamoDB schema (single-table)

| Item | PK | SK |
| --- | --- | --- |
| User | `USER#<google_id>` | `#META` |
| Feed | `USER#<google_id>` | `FEED#<feed_id>` |
| Article | `FEED#<feed_id>` | `ARTICLE#<published_at>#<guid_hash>` |
| GUID sentinel | `FEED#<feed_id>` | `GUID#<guid_hash>` |

**GSI1** (`GSI1PK=ALL_FEEDS`) — all feeds across all users, used by the EventBridge scheduler.

**GSI2** (`GSI2PK=USER#<id>`, `GSI2SK=<published_at>#<guid_hash>`) — a user's articles sorted newest-first across all feeds.

Article IDs exposed in the API are opaque base64url-encoded strings (`feed_id:SK`). Pagination cursors are base64url-encoded `LastEvaluatedKey` dicts.
