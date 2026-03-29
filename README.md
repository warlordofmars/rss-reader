# RSS Reader

A full-stack RSS reader with Google OAuth, deployed on AWS.

**Live at [rss.warlordofmars.net](https://rss.warlordofmars.net)**

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

## Project Structure

```
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
uv run inv outputs --env <name> # show outputs for a named environment
uv run inv logs                 # tail prod Lambda CloudWatch logs
uv run inv logs --env <name>    # tail logs for a named environment
uv run inv clean                # remove build artifacts
```

Sub-tasks: `lint-backend`, `lint-frontend`, `lint-infra`, `test-backend`, `test-frontend`, `synth`.

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
  --secret-string '{"GOOGLE_CLIENT_ID":"...","GOOGLE_CLIENT_SECRET":"...","JWT_SECRET":"..."}'

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
  --secret-string '{"GOOGLE_CLIENT_ID":"...","GOOGLE_CLIENT_SECRET":"...","JWT_SECRET":"..."}'

# 3. Add OAuth redirect URI in Google Cloud Console
#    https://api.rss-<name>.warlordofmars.net/auth/callback
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
