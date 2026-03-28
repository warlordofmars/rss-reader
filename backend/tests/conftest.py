from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, Feed, User, get_db
from main import app, create_jwt


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # all sessions share the same in-memory DB
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture()
def TestSession(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db(TestSession):
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def client(TestSession):
    def override_get_db():
        s = TestSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db

    with patch("main.start_scheduler"), patch("main.stop_scheduler"):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def patch_fetcher_session(TestSession):
    """Redirect fetcher.SessionLocal to the test DB."""
    with patch("fetcher.SessionLocal", TestSession):
        yield


@pytest.fixture()
def user(db):
    u = User(google_id="google-123", email="test@example.com", name="Test User", picture="")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture()
def auth_headers(user):
    token = create_jwt(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def feed(db, user):
    f = Feed(user_id=user.id, url="https://example.com/feed.xml", title="Example Feed")
    db.add(f)
    db.commit()
    db.refresh(f)
    return f
