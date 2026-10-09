#!/bin/bash

# Setup script for mcelveen-oauth-tokens DynamoDB table
# Run this after deploying v3.0.32+ to create the OAuth token storage table

set -e

TABLE_NAME="mcelveen-oauth-tokens"
REGION="us-east-2"

echo "[SETUP] Creating DynamoDB table: $TABLE_NAME"

aws dynamodb create-table \
  --table-name "$TABLE_NAME" \
  --attribute-definitions \
    AttributeName=token_id,AttributeType=S \
  --key-schema \
    AttributeName=token_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" \
  --ttl-specification Enabled=true,AttributeName=ttl

echo "[SUCCESS] Table created: $TABLE_NAME"
echo "[INFO] Table will be in CREATING state for a few seconds"
echo "[INFO] Environment variable OAUTH_TOKENS_TABLE defaults to: $TABLE_NAME"
echo "[INFO] Next: Get new SCHWAB_REFRESH_TOKEN from OAuth Playground and update Lambda environment"
