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
uv run inv --list               # show all tasks
uv run inv dev                  # start backend + frontend locally (Ctrl-C to stop)
uv run inv lint                 # lint everything
uv run inv test                 # run all tests
uv run inv deploy               # deploy prod to AWS via CDK
uv run inv deploy --env dev     # deploy dev environment
uv run inv deploy --env <name>  # deploy arbitrary named environment
uv run inv outputs              # print prod CloudFormation stack outputs
uv run inv outputs --env dev    # print dev stack outputs
uv run inv outputs --env <name> # print outputs for any named environment
uv run inv logs                 # tail prod Lambda CloudWatch logs
uv run inv logs --env dev       # tail dev Lambda CloudWatch logs
uv run inv logs --env <name>    # tail logs for any named environment
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

- `stacks/rss_reader_stack.py` — single CDK stack defining all AWS resources, parameterized by `env_name`
- `app.py` — CDK app entry point; reads `env` context to select stack name and config

## Branching & Release Workflow

Two permanent branches:

- `development` — default branch; merges auto-deploy to dev (`rss-dev.warlordofmars.net`)
- `main` — production; merges trigger semantic-release and auto-deploy to prod (`rss.warlordofmars.net`)

**Feature work:** branch from `development` → PR → `development` using **squash merge**.

**Prod release:** PR from `development` → `main` using **merge commit** (not squash). This preserves all individual conventional commits so semantic-release can compute the correct version bump. After merging, CI runs semantic-release, deploys to prod, then automatically opens a back-merge PR (`main` → `development`) with auto-merge enabled — it merges itself once CI passes.

**Back-merge conflicts:** If the auto back-merge PR has conflicts, resolve them on a branch → PR into `development` → back-merge will then merge cleanly. Manual trigger: `uv run inv back-merge`.

**Version format:**

- Prod: `MAJOR.MINOR.PATCH` (e.g. `1.2.0`)
- Dev: `MAJOR.MINOR.PATCH-dev.<short-sha>` (e.g. `1.2.0-dev.aa584cd`) — inferred next version + SHA

## Environments

The stack supports arbitrary named environments. `prod` is special; everything else follows a naming convention.

| env | Frontend | API |
| --- | --- | --- |
| `prod` | `rss.warlordofmars.net` | `api.rss.warlordofmars.net` |
| `dev` | `rss-dev.warlordofmars.net` | `api.rss-dev.warlordofmars.net` |
| `<name>` | `rss-<name>.warlordofmars.net` | `api.rss-<name>.warlordofmars.net` |

Deploy with `uv run inv deploy --env <name>`. After first deploy of a new env, three manual steps are required — see the Deployment section in README.md.

## DynamoDB schema (single-table)

| Item | PK | SK |
| --- | --- | --- |
| User | `USER#<google_id>` | `#META` |
| Feed | `USER#<google_id>` | `FEED#<feed_id>` |
| Article | `FEED#<feed_id>` | `ARTICLE#<published_at>#<guid_hash>` |
| GUID sentinel | `FEED#<feed_id>` | `GUID#<guid_hash>` |

GSI1: `ALL_FEEDS` partition → all feeds (EventBridge scheduler)
GSI2: `USER#<id>` partition + date sort → user's articles newest-first
