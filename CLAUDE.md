# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

- **Backend:** FastAPI, SQLAlchemy (SQLite), feedparser, APScheduler — runs on port 8000
- **Frontend:** React + Vite — runs on port 5173

## Commands

### Backend
```bash
cd backend
uv sync                            # install deps from pyproject.toml
uv run uvicorn main:app --reload   # start dev server
```

### Frontend
```bash
cd frontend
npm install
npm run dev                        # start dev server
npm run build
npm run lint
```

## Architecture

Full-stack app where the React frontend communicates exclusively with FastAPI REST endpoints.

**Backend layout (`backend/`):**
- `main.py` — FastAPI app entry point, route definitions, CORS config
- `db.py` — SQLAlchemy models and database logic (SQLite)
- `fetcher.py` — RSS feed fetching via feedparser
- `scheduler.py` — APScheduler job that auto-refreshes all feeds every 30 minutes

**Frontend layout (`frontend/src/`):**
- `App.jsx` — root component and app-level state
- `components/` — UI components

## Features

- Add/remove RSS feed URLs
- Article list sorted by date with a reading view
- Mark articles as read/unread
- Keyword filtering
- Auto-refresh every 30 minutes via APScheduler
