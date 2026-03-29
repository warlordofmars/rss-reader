# RSS Reader

A full-stack RSS reader with Google OAuth, deployed on AWS.

**Live at [rss.warlordofmars.net](https://rss.warlordofmars.net)** | **Dev at [rss-dev.warlordofmars.net](https://rss-dev.warlordofmars.net)**

## Stack

| Layer | Tech |
| --- | --- |
| Backend | FastAPI, boto3/DynamoDB, feedparser, Mangum |
| Frontend | React, Vite, shadcn/ui, Tailwind CSS |
| Auth | Google OAuth 2.0 + JWT |
| Infra | AWS CDK (Python) |
| CI/CD | GitHub Actions + OIDC |

## Features

- Sign in with Google
- Add and remove RSS feed URLs
- Articles sorted by date with inline reading view
- Mark articles as read / unread
- Keyword filtering across title and content
- Auto-refresh all feeds every 30 minutes (EventBridge)
- Admin interface at `/admin` — user list with engagement metrics and CloudWatch links

## Project Structure

```text
rss-reader/
├── backend/
│   ├── main.py          # FastAPI app, routes, auth
│   ├── db.py            # DynamoDB single-table data layer
│   ├── fetcher.py       # feedparser-based article ingestion
│   ├── handler.py       # Lambda entry point (Mangum)
│   ├── scheduler.py     # APScheduler (local dev only)
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── lib/api.js   # API client
│   │   └── components/
│   └── package.json
├── infra/
│   └── stacks/
│       └── rss_reader_stack.py   # CDK stack
└── tasks.py             # Invoke task runner
```

## Getting Started (local dev)

### Prerequisites

- Python 3.11+ with [uv](https://astral.sh/uv)
- Node.js 20+
- AWS credentials configured (`~/.aws`) with access to the deployed stack

### 1. Install dependencies

```bash
uv sync          # root invoke tasks
cd backend && uv sync
cd frontend && npm install
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
# Fill in: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET,
#          DYNAMODB_TABLE, CONTENT_BUCKET (from CloudFormation outputs)
```

Get the table and bucket names:

```bash
uv run inv outputs
```

### 3. Add OAuth redirect URI

In [Google Cloud Console](https://console.cloud.google.com) → your OAuth app → **Authorized redirect URIs**, add:

```text
http://localhost:8000/auth/callback
```

### 4. Start the app

```bash
uv run inv dev
```

Backend at `http://localhost:8000`, frontend at `http://localhost:5173`.

## Tasks

All common operations are available via `invoke`:

```bash
uv run inv --list               # show all tasks
uv run inv dev                  # start backend + frontend locally
uv run inv lint                 # lint everything
uv run inv test                 # run all tests
uv run inv deploy               # deploy prod to AWS
uv run inv deploy --env <name>  # deploy a named environment
uv run inv outputs              # show prod CloudFormation stack outputs
uv run inv outputs --env dev    # show dev stack outputs
uv run inv outputs --env <name> # show outputs for any named environment
uv run inv logs                 # tail prod Lambda CloudWatch logs
uv run inv logs --env dev       # tail dev Lambda logs
uv run inv logs --env <name>    # tail logs for any named environment
uv run inv clean                # remove build artifacts
```

Sub-tasks: `lint-backend`, `lint-frontend`, `lint-infra`, `test-backend`, `test-frontend`, `synth`.

## Branching & Release Workflow

This repo uses a two-branch model:

| Branch | Environment | Deploys on |
| --- | --- | --- |
| `development` | dev (`rss-dev.warlordofmars.net`) | every merge |
| `main` | prod (`rss.warlordofmars.net`) | every merge |

### Day-to-day: feature work

```text
feature-branch → PR → development  (squash merge)
```

- Branch from `development`
- Open a PR targeting `development`; CI runs lint + tests
- Merge using **squash merge** — one clean commit lands on `development`
- A successful merge auto-deploys to dev

### Releasing to prod

```text
development → PR → main  (merge commit)
                ↓
        semantic-release
        GitHub release + tag
        deploy to prod
                ↓
        auto back-merge PR
        main → development  (auto-merges when CI passes)
```

1. Open a PR from `development` → `main`
2. CI runs lint + tests
3. Merge using **merge commit** (not squash) — this preserves all individual commits so the versioning script can compute the correct bump (`feat:` → minor, breaking → major, anything else → patch)
4. CI then automatically:
   - Bumps the version, creates a git tag and GitHub release
   - Deploys to prod
   - Opens a back-merge PR (`main` → `development`) and enables auto-merge on it
5. The back-merge PR merges automatically once CI passes — no action needed

> **Note:** If the back-merge PR has conflicts, resolve them on a branch and PR into `development` first, then the back-merge will merge cleanly. You can also trigger the back-merge PR manually: `uv run inv back-merge`

### Version numbers

| Context | Format | Example |
| --- | --- | --- |
| Prod release | `MAJOR.MINOR.PATCH` | `1.2.0` |
| Dev deploy | `MAJOR.MINOR.PATCH-dev.<sha>` | `1.2.0-dev.aa584cd` |

The dev version reflects the *inferred next* version based on commits since the last tag, plus the short git SHA for uniqueness between deploys.

## Deployment

### Prod (first-time setup)

```bash
# 1. Bootstrap CDK (once per account/region)
cd infra && uv run cdk bootstrap -c account=<account-id>

# 2. Deploy
uv run inv deploy

# 3. Populate secrets (get AppSecretArn from outputs)
uv run inv outputs
aws secretsmanager put-secret-value \
  --secret-id <AppSecretArn> \
  --secret-string '{"GOOGLE_CLIENT_ID":"...","GOOGLE_CLIENT_SECRET":"...","JWT_SECRET":"...","ADMIN_PASSWORD":"..."}'

# 4. Add GitHub secrets for CI/CD
#    AWS_DEPLOY_ROLE_ARN  →  GitHubActionsDeployRoleArn output
#    AWS_ACCOUNT_ID       →  your 12-digit account ID
```

After that, every push to `main` deploys automatically via GitHub Actions.

### Named environments (dev, jcarter, etc.)

Any environment name is supported. Domains are derived automatically:

- Frontend: `https://rss-<name>.warlordofmars.net`
- API: `https://api.rss-<name>.warlordofmars.net`

```bash
# 1. Deploy
uv run inv deploy --env <name>

# 2. Populate secrets (get AppSecretArn from outputs)
uv run inv outputs --env <name>
aws secretsmanager put-secret-value \
  --secret-id <AppSecretArn> \
  --secret-string '{"GOOGLE_CLIENT_ID":"...","GOOGLE_CLIENT_SECRET":"...","JWT_SECRET":"...","ADMIN_PASSWORD":"..."}'

# 3. Add OAuth redirect URI in Google Cloud Console
#    https://api.rss-<name>.warlordofmars.net/auth/callback

# Ongoing — check outputs or tail logs at any time
uv run inv outputs --env <name>
uv run inv logs --env <name>
```

To deploy `dev` from GitHub Actions, trigger the **Deploy Dev** workflow manually from the Actions tab. Set `AWS_DEV_DEPLOY_ROLE_ARN` in GitHub secrets to the `GitHubActionsDeployRoleArn` output from the dev stack.

## Environment Variables

| Variable | Description |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `JWT_SECRET` | Secret key for signing JWTs |
| `REDIRECT_URI` | OAuth callback URL (default: `http://localhost:8000/auth/callback`) |
| `FRONTEND_URL` | Frontend origin (default: `http://localhost:5173`) |
| `DYNAMODB_TABLE` | DynamoDB table name (from CloudFormation output) |
| `CONTENT_BUCKET` | S3 bucket for article content overflow |
| `AWS_REGION` | AWS region (default: `us-east-1`) |
| `ADMIN_PASSWORD` | Password for `/admin` HTTP Basic Auth (default: `admin`) |
