import os
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import Article, Feed, User, get_db, init_db
from fetcher import fetch_feed
from scheduler import start_scheduler, stop_scheduler

load_dotenv()

app = FastAPI(title="RSS Reader API")

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


@app.on_event("startup")
async def startup():
    init_db()
    start_scheduler()


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()


# ── Helpers ───────────────────────────────────────────────────────────────────


def create_jwt(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_user_article(article_id: int, current_user: User, db: Session) -> Article:
    user_feed_ids = [
        row[0] for row in db.query(Feed.id).filter(Feed.user_id == current_user.id).all()
    ]
    article = (
        db.query(Article)
        .filter(Article.id == article_id, Article.feed_id.in_(user_feed_ids))
        .first()
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


# ── Auth ──────────────────────────────────────────────────────────────────────


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
async def auth_callback(code: str, db: Session = Depends(get_db)):
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

    user = db.query(User).filter(User.google_id == info["sub"]).first()
    if not user:
        user = User(
            google_id=info["sub"],
            email=info["email"],
            name=info["name"],
            picture=info.get("picture", ""),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_jwt(user.id, user.email)
    return RedirectResponse(f"{FRONTEND_URL}?token={token}")


@app.get("/auth/me")
def auth_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
    }


# ── Feeds ─────────────────────────────────────────────────────────────────────


class AddFeedRequest(BaseModel):
    url: str


@app.get("/feeds")
def list_feeds(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    feeds = db.query(Feed).filter(Feed.user_id == current_user.id).all()
    return [
        {
            "id": f.id,
            "url": f.url,
            "title": f.title or f.url,
            "created_at": f.created_at,
            "unread_count": db.query(Article)
            .filter(Article.feed_id == f.id, Article.is_read == False)
            .count(),
        }
        for f in feeds
    ]


@app.post("/feeds", status_code=201)
def add_feed(
    body: AddFeedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(Feed)
        .filter(Feed.user_id == current_user.id, Feed.url == body.url)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Feed already added")

    feed = Feed(user_id=current_user.id, url=body.url)
    db.add(feed)
    db.commit()
    db.refresh(feed)

    threading.Thread(target=fetch_feed, args=(feed.id,), daemon=True).start()

    return {"id": feed.id, "url": feed.url, "title": feed.title or feed.url}


@app.delete("/feeds/{feed_id}", status_code=204)
def delete_feed(
    feed_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    feed = (
        db.query(Feed)
        .filter(Feed.id == feed_id, Feed.user_id == current_user.id)
        .first()
    )
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    db.delete(feed)
    db.commit()


@app.post("/feeds/{feed_id}/refresh")
def refresh_feed(
    feed_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    feed = (
        db.query(Feed)
        .filter(Feed.id == feed_id, Feed.user_id == current_user.id)
        .first()
    )
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    threading.Thread(target=fetch_feed, args=(feed.id,), daemon=True).start()
    return {"status": "refreshing"}


# ── Articles ──────────────────────────────────────────────────────────────────


@app.get("/articles")
def list_articles(
    feed_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    unread_only: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_feed_ids = [
        row[0] for row in db.query(Feed.id).filter(Feed.user_id == current_user.id).all()
    ]

    q = db.query(Article).filter(Article.feed_id.in_(user_feed_ids))

    if feed_id is not None:
        if feed_id not in user_feed_ids:
            raise HTTPException(status_code=403, detail="Not your feed")
        q = q.filter(Article.feed_id == feed_id)

    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            Article.title.ilike(like)
            | Article.content.ilike(like)
            | Article.summary.ilike(like)
        )

    if unread_only:
        q = q.filter(Article.is_read == False)

    articles = q.order_by(Article.published_at.desc()).limit(200).all()

    return [
        {
            "id": a.id,
            "feed_id": a.feed_id,
            "title": a.title,
            "link": a.link,
            "content": a.content or a.summary,
            "published_at": a.published_at,
            "is_read": a.is_read,
        }
        for a in articles
    ]


@app.patch("/articles/{article_id}/read")
def mark_read(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = get_user_article(article_id, current_user, db)
    article.is_read = True
    db.commit()
    return {"id": article.id, "is_read": True}


@app.patch("/articles/{article_id}/unread")
def mark_unread(
    article_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    article = get_user_article(article_id, current_user, db)
    article.is_read = False
    db.commit()
    return {"id": article.id, "is_read": False}
