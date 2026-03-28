#!/usr/bin/env bash
# Creates the DynamoDB table and S3 bucket in LocalStack for local development.
# Run once after `docker-compose up -d`.
set -euo pipefail

ENDPOINT=http://localhost:4566
TABLE=rss-reader
BUCKET=rss-reader-content

aws_local() {
  aws --endpoint-url "$ENDPOINT" --region us-east-1 "$@"
}

echo "Waiting for LocalStack..."
until aws_local dynamodb list-tables &>/dev/null; do
  sleep 1
done

echo "Creating DynamoDB table: $TABLE"
aws_local dynamodb create-table \
  --table-name "$TABLE" \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=GSI1PK,AttributeType=S \
    AttributeName=GSI1SK,AttributeType=S \
    AttributeName=GSI2PK,AttributeType=S \
    AttributeName=GSI2SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --global-secondary-indexes \
    '[
      {
        "IndexName": "GSI1",
        "KeySchema": [
          {"AttributeName":"GSI1PK","KeyType":"HASH"},
          {"AttributeName":"GSI1SK","KeyType":"RANGE"}
        ],
        "Projection": {
          "ProjectionType": "INCLUDE",
          "NonKeyAttributes": ["feed_id","user_id","url","title"]
        }
      },
      {
        "IndexName": "GSI2",
        "KeySchema": [
          {"AttributeName":"GSI2PK","KeyType":"HASH"},
          {"AttributeName":"GSI2SK","KeyType":"RANGE"}
        ],
        "Projection": {
          "ProjectionType": "INCLUDE",
          "NonKeyAttributes": ["feed_id","title","link","summary","published_at","is_read","content_s3_key"]
        }
      }
    ]' \
  --billing-mode PAY_PER_REQUEST \
  2>&1 | grep -v "already exists" || true

echo "Creating S3 bucket: $BUCKET"
aws_local s3 mb "s3://$BUCKET" 2>&1 | grep -v "already exists" || true

echo "Done."
