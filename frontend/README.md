# Frontend

React + Vite single-page application for the RSS Reader. Deployed to S3 + CloudFront at [rss.warlordofmars.net](https://rss.warlordofmars.net).

## Local dev

```bash
npm install
npm run dev
```

App available at `http://localhost:5173`. Requires the backend running at `http://localhost:8000` (or set `VITE_API_URL`).

Or from the repo root:

```bash
uv run inv dev   # starts both backend and frontend
```

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_URL` | `http://localhost:8000` | Backend API base URL |

Create a `.env.local` file to override locally. In production, `VITE_API_URL` is injected at build time by CDK (`https://api.rss.warlordofmars.net`).

## Commands

```bash
uv run inv dev            # start both backend + frontend (from repo root)
uv run inv lint-frontend  # ESLint
uv run inv test-frontend  # Vitest
```

Or directly via npm:

```bash
npm run dev      # start dev server
npm run build    # production build → dist/
npm run lint     # ESLint
npm test         # Vitest
```

## Layout

```text
src/
├── App.jsx              # root component, auth state, token handling
├── lib/
│   └── api.js           # API client (fetch wrapper, JWT injection)
└── components/
    ├── FeedSidebar.jsx  # feed list + add/delete
    ├── ArticleList.jsx  # article list with pagination, filters
    └── ArticleView.jsx  # article reading view
```
