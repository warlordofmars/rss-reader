from unittest.mock import patch

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

TABLE_NAME = "rss-reader-test"
BUCKET_NAME = "rss-reader-content-test"


# ── AWS / moto bootstrap ──────────────────────────────────────────────────────


@pytest.fixture()
def aws(monkeypatch):
    """
    Activate moto mocks for DynamoDB + S3, create the table and content bucket,
    and point the app at them via environment variables.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("DYNAMODB_TABLE", TABLE_NAME)
    monkeypatch.setenv("CONTENT_BUCKET", BUCKET_NAME)

    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
                {"AttributeName": "GSI2PK", "AttributeType": "S"},
                {"AttributeName": "GSI2SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1",
                    "KeySchema": [
                        {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "GSI2",
                    "KeySchema": [
                        {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                        {"AttributeName": "GSI2SK", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=BUCKET_NAME)

        yield {"table": table, "s3": s3}


# ── App-level fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def client(aws):
    with patch("main.start_scheduler"), patch("main.stop_scheduler"):
        from main import app

        with TestClient(app) as c:
            yield c


# ── Data fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture()
def user(aws):
    import db as _db

    return _db.upsert_user("google-123", "test@example.com", "Test User", "")


@pytest.fixture()
def auth_headers(user):
    from main import create_jwt

    token = create_jwt(user["google_id"], user["email"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def feed(aws, user):
    import db as _db

    return _db.create_feed(user["google_id"], "https://example.com/feed.xml", title="Example Feed")
