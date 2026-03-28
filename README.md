# RSS Reader

A full-stack RSS reader with Google OAuth, built with FastAPI and React.

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy (SQLite), feedparser, APScheduler |
| Frontend | React, Vite, shadcn/ui, Tailwind CSS |
| Auth | Google OAuth 2.0 + JWT |
| Package management | `uv` (Python), `npm` (Node) |

## Features

- Sign in with Google
- Add and remove RSS feed URLs
- Articles sorted by date with inline reading view
- Mark articles as read / unread
- Keyword filtering across title and content
- Auto-refresh all feeds every 30 minutes

## Project Structure

```
rss-reader/
├── backend/
│   ├── main.py          # FastAPI app, routes, auth
│   ├── db.py            # SQLAlchemy models (User, Feed, Article)
│   ├── fetcher.py       # feedparser-based article ingestion
│   ├── scheduler.py     # APScheduler 30-min refresh job
│   ├── pyproject.toml   # Python deps (managed by uv)
│   └── .env.example     # Required environment variables
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── lib/api.js   # API client
    │   └── components/  # Layout, FeedSidebar, ArticleList, ArticleView, …
    └── package.json
```

## Getting Started

### 1. Google OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com) and create a project
2. Navigate to **APIs & Services → OAuth consent screen** and configure it
3. Go to **Credentials → Create Credentials → OAuth client ID** (Web application)
4. Add `http://localhost:8000/auth/callback` as an authorised redirect URI
5. Copy the Client ID and Client Secret

### 2. Backend

```bash
cd backend

# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Create your .env
cp .env.example .env
# Edit .env and fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET

# Start the dev server
uv run uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

## Running Tests

### Backend

```bash
cd backend
uv run pytest tests/ -v
```

### Frontend

```bash
cd frontend
npm test
```

Tests run automatically after every file change via a Claude Code hook.

## Environment Variables

| Variable | Description |
|---|---|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `JWT_SECRET` | Secret key for signing JWTs (use a long random string) |
| `REDIRECT_URI` | OAuth callback URL (default: `http://localhost:8000/auth/callback`) |
| `FRONTEND_URL` | Frontend origin (default: `http://localhost:5173`) |
