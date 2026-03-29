import os
import threading
import urllib.parse
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

import db
from fetcher import fetch_feed
from scheduler import start_scheduler, stop_scheduler

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DynamoDB table is pre-created via CDK; no init_db() needed.
    # Skip the scheduler in Lambda — EventBridge handles periodic fetching (Phase 4).
    in_lambda = bool(os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
    if not in_lambda:
        start_scheduler()
    yield
    if not in_lambda:
        stop_scheduler()


app = FastAPI(title="RSS Reader API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGORITHM = "HS256"
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

security = HTTPBearer()


# ── Auth helpers ───────────────────────────────────────────────────────────────


def create_jwt(google_id: str, email: str) -> str:
    payload = {
        "sub": google_id,
        "email": email,
        "exp": datetime.now(UTC) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        google_id = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.get_user(google_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Version ───────────────────────────────────────────────────────────────────


@app.get("/version")
def version():
    return {"version": os.getenv("APP_VERSION", "dev")}


# ── Auth routes ────────────────────────────────────────────────────────────────


@app.get("/auth/login")
def auth_login():
    params = urllib.parse.urlencode(
        {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
        }
    )
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.get("/auth/callback")
async def auth_callback(code: str):
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()

    user = db.upsert_user(
        google_id=info["sub"],
        email=info["email"],
        name=info["name"],
        picture=info.get("picture", ""),
    )

    token = create_jwt(user["google_id"], user["email"])
    return RedirectResponse(f"{FRONTEND_URL}?token={token}")


@app.get("/auth/me")
def auth_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["google_id"],
        "email": current_user["email"],
        "name": current_user["name"],
        "picture": current_user.get("picture", ""),
    }


# ── Feed routes ────────────────────────────────────────────────────────────────


class AddFeedRequest(BaseModel):
    url: str


@app.get("/feeds")
def list_feeds(current_user: dict = Depends(get_current_user)):
    return db.list_feeds(current_user["google_id"])


@app.post("/feeds", status_code=201)
def add_feed(body: AddFeedRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["google_id"]

    if db.check_feed_url_exists(user_id, body.url):
        raise HTTPException(status_code=409, detail="Feed already added")

    feed = db.create_feed(user_id, body.url)

    # Fetch in background using the raw dict (includes all keys fetcher needs)
    raw = db.get_feed_raw(user_id, feed["id"])
    if raw:
        threading.Thread(target=fetch_feed, args=(raw,), daemon=True).start()

    return feed


@app.delete("/feeds/{feed_id}", status_code=204)
def delete_feed(feed_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["google_id"]
    if not db.get_feed(user_id, feed_id):
        raise HTTPException(status_code=404, detail="Feed not found")
    db.delete_feed(user_id, feed_id)


@app.post("/feeds/{feed_id}/refresh")
def refresh_feed(feed_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["google_id"]
    raw = db.get_feed_raw(user_id, feed_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Feed not found")
    threading.Thread(target=fetch_feed, args=(raw,), daemon=True).start()
    return {"status": "refreshing"}


# ── Article routes ─────────────────────────────────────────────────────────────


@app.get("/articles")
def list_articles(
    feed_id: str | None = Query(None),
    keyword: str | None = Query(None),
    unread_only: bool = Query(False),
    limit: int = Query(25, ge=1, le=100),
    cursor: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    user_id = current_user["google_id"]

    if feed_id is not None and not db.get_feed(user_id, feed_id):
        raise HTTPException(status_code=403, detail="Not your feed")

    items, next_cursor = db.list_articles(
        user_id=user_id,
        feed_id=feed_id,
        limit=limit,
        cursor=cursor,
        unread_only=unread_only,
        keyword=keyword,
    )
    return {"items": items, "next_cursor": next_cursor}


@app.patch("/articles/{article_id}/read")
def mark_read(article_id: str, current_user: dict = Depends(get_current_user)):
    feed_id, article_sk = db.decode_article_id(article_id)
    result = db.mark_article_read(feed_id, article_sk, current_user["google_id"], is_read=True)
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return result


@app.patch("/articles/{article_id}/unread")
def mark_unread(article_id: str, current_user: dict = Depends(get_current_user)):
    feed_id, article_sk = db.decode_article_id(article_id)
    result = db.mark_article_read(feed_id, article_sk, current_user["google_id"], is_read=False)
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return result
