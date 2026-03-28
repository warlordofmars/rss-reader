# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

- **Backend:** FastAPI, boto3/DynamoDB, feedparser, Mangum (Lambda adapter) — runs on port 8000
- **Frontend:** React + Vite — runs on port 5173
- **Infra:** AWS CDK (Python) — DynamoDB, S3, Lambda, API Gateway, CloudFront, Route53
- **Deployed:** `rss.warlordofmars.net` (frontend), `api.rss.warlordofmars.net` (API)

## Commands

All common tasks are available via `invoke` from the repo root:

```bash
uv run inv --list          # show all tasks
uv run inv dev             # start backend + frontend locally (Ctrl-C to stop)
uv run inv lint            # lint everything
uv run inv test            # run all tests
uv run inv deploy          # deploy to AWS via CDK
uv run inv outputs         # print CloudFormation stack outputs
uv run inv logs            # tail Lambda CloudWatch logs
```

Individual tasks: `lint-backend`, `lint-frontend`, `lint-infra`, `test-backend`, `test-frontend`, `synth`, `clean`.

### Local dev prerequisites

- AWS credentials configured (`~/.aws`) with access to the deployed DynamoDB table and S3 bucket
- `backend/.env` populated with `DYNAMODB_TABLE`, `CONTENT_BUCKET`, `AWS_REGION`, and Google OAuth secrets

## Architecture

**Backend layout (`backend/`):**

- `main.py` — FastAPI app, route definitions, CORS, Google OAuth, JWT auth
- `db.py` — DynamoDB single-table data layer (boto3)
- `fetcher.py` — RSS feed fetching via feedparser
- `handler.py` — AWS Lambda entry point (loads Secrets Manager, wraps app with Mangum)
- `scheduler.py` — APScheduler (local dev only; EventBridge handles scheduling in Lambda)

**Frontend layout (`frontend/src/`):**

- `App.jsx` — root component and app-level state
- `components/` — UI components
- `lib/api.js` — API client (reads `VITE_API_URL` env var)

**Infra layout (`infra/`):**

- `stacks/rss_reader_stack.py` — single CDK stack defining all AWS resources

## DynamoDB schema (single-table)

| Item | PK | SK |
| --- | --- | --- |
| User | `USER#<google_id>` | `#META` |
| Feed | `USER#<google_id>` | `FEED#<feed_id>` |
| Article | `FEED#<feed_id>` | `ARTICLE#<published_at>#<guid_hash>` |
| GUID sentinel | `FEED#<feed_id>` | `GUID#<guid_hash>` |

GSI1: `ALL_FEEDS` partition → all feeds (EventBridge scheduler)
GSI2: `USER#<id>` partition + date sort → user's articles newest-first
