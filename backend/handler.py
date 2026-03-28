"""
AWS Lambda entry point.

Secrets are loaded from Secrets Manager before main.py is imported so that
all os.getenv() calls in main.py (JWT_SECRET, GOOGLE_CLIENT_ID, etc.) pick
up the correct values on every cold start.
"""

import json
import os

import boto3


def _load_secrets() -> None:
    arn = os.getenv("APP_SECRET_ARN")
    if not arn:
        return  # running locally — secrets come from .env file
    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
    resp = client.get_secret_value(SecretId=arn)
    for key, value in json.loads(resp["SecretString"]).items():
        os.environ.setdefault(key, value)


_load_secrets()

import fetcher  # noqa: E402
from main import app  # noqa: E402 — must import after secrets are injected
from mangum import Mangum  # noqa: E402

_mangum = Mangum(app, lifespan="off")


def handler(event, context):
    # EventBridge scheduled events have source == "aws.events"
    if event.get("source") == "aws.events":
        fetcher.fetch_all_feeds()
        return {"status": "ok"}
    return _mangum(event, context)
