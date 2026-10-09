# McElveen Autonomous Trading System - v3.0.32 Deployment Guide

## What's New in v3.0.32

**FIX: Automatic OAuth Token Rotation** (Fixes HTTP 400 Token Refresh Failure)

Schwab refresh tokens expire every **7 days**. The v3.0.31 code failed because it didn't capture the new refresh token from Schwab's response. 

v3.0.32 now:
1. ✅ Captures the new refresh_token from each OAuth response (Schwab includes it with every token refresh)
2. ✅ Stores it in a dedicated DynamoDB table (`mcelveen-oauth-tokens`)
3. ✅ Retrieves and uses the stored token on next execution
4. ✅ Never expires—automatically cycles every 7 days without manual intervention

---

## Step 1: Create the OAuth Tokens Table (CRITICAL)

The v3.0.32 code uses a new dedicated DynamoDB table: `mcelveen-oauth-tokens`

**Option A: AWS Console**

1. Go to [AWS DynamoDB Console](https://console.aws.amazon.com/dynamodb)
2. Click **Create table**
3. Enter:
   - **Table name:** `mcelveen-oauth-tokens`
   - **Partition key:** `token_id` (String)
   - **Billing mode:** Pay-per-request
4. Click **Create**
5. After table appears, go to **Time to live (TTL)**
   - Click **Manage TTL**
   - Attribute name: `ttl`
   - Click **Enable**

**Option B: AWS CLI**

```bash
aws dynamodb create-table \
  --table-name mcelveen-oauth-tokens \
  --attribute-definitions AttributeName=token_id,AttributeType=S \
  --key-schema AttributeName=token_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-2 \
  --ttl-specification Enabled=true,AttributeName=ttl
```

**Option C: Run Provided Script**

```bash
cd /home/claude/mcelveen-autonomous-trading-system
chmod +x setup_oauth_table.sh
./setup_oauth_table.sh
```

---

## Step 2: Get New Schwab Refresh Token

**Why?** The old SCHWAB_REFRESH_TOKEN in Lambda environment is likely expired (7 days old). We need a fresh one.

1. Go to [Schwab OAuth Playground](https://developer.schwab.com/oauth)
2. Select **Account Access Delegation (AAD)** flow
3. Enter your `SCHWAB_CLIENT_ID` and `SCHWAB_CLIENT_SECRET`
4. Click **Authorize**
5. Login with your Schwab credentials
6. Accept permissions
7. **Copy the `refresh_token`** (long string starting with `ey...`)
   - This is valid for 7 days
   - v3.0.32 will automatically capture new tokens from Schwab on each refresh

---

## Step 3: Update Lambda Environment Variable

1. Go to [AWS Lambda Console](https://console.aws.amazon.com/lambda)
2. Find function: `mcelveen-trading-system`
3. Click **Configuration** → **Environment variables**
4. Find `SCHWAB_REFRESH_TOKEN`
5. Paste the new refresh token from Step 2
6. Click **Save**

Wait 1-2 minutes for Lambda to reload environment.

---

## Step 4: Verify Deployment

The next Lambda execution will:
1. Read refresh token from environment (or DynamoDB if stored)
2. Call Schwab OAuth endpoint to get new access token
3. **Capture the new refresh_token from the response** (v3.0.32 FIX)
4. Store it in DynamoDB with 8-day TTL
5. Execute trades using the fresh access token

**Check CloudWatch Logs:**

```bash
aws logs tail /aws/lambda/mcelveen-trading-system --follow
```

**Expected output on success:**
```
[OAUTH] ✅ Retrieved refresh token from DynamoDB (OAUTH_TOKENS_TABLE)
[OAUTH] ✅ Token refreshed (expires in 1800s)
[INIT] ✅ Schwab authentication successful
```

**If you see this error:**
```
[WARN] Failed to retrieve token from DynamoDB: ValidationException...
[OAUTH] Using refresh token from environment
```

This is **OK** on the first run after creating the table (token not yet stored). On the next execution, it should retrieve from DynamoDB.

---

## How v3.0.32 Automatic Token Rotation Works

```
Execution 1 (Day 0):
  ├─ Environment has SCHWAB_REFRESH_TOKEN (expires day 7)
  ├─ Call Schwab: GET new access token
  ├─ Schwab responds with new refresh_token (valid day 0–7)
  ├─ Store new refresh_token in DynamoDB
  └─ Trade using access token

Execution 2 (Day 1):
  ├─ Retrieve refresh_token from DynamoDB (stored from Execution 1)
  ├─ Call Schwab: GET new access token
  ├─ Schwab responds with another new refresh_token (valid day 1–8)
  ├─ Store updated refresh_token in DynamoDB
  └─ Trade using access token

Execution N (Day 30+):
  ├─ Always has fresh refresh_token from prior execution
  ├─ Never expires because we capture & store new one every time
  └─ System runs indefinitely ✅
```

---

## Environment Variable Configuration

After v3.0.32 deployment, Lambda should have:

| Variable | Value | Source |
|----------|-------|--------|
| `SCHWAB_CLIENT_ID` | Your app's client ID | Schwab Developer Portal |
| `SCHWAB_CLIENT_SECRET` | Your app's secret | Schwab Developer Portal |
| `SCHWAB_REFRESH_TOKEN` | New token from Step 2 | Schwab OAuth Playground (one-time initial setup) |
| `CLAUDE_API_KEY` | Your Anthropic API key | Anthropic Console |
| `OAUTH_TOKENS_TABLE` | `mcelveen-oauth-tokens` | (optional—defaults to this name) |
| `EXECUTION_LOG_TABLE` | `mcelveen-execution-log` | (from earlier setup) |

---

## Troubleshooting v3.0.32

### Issue: "ValidationException: The provided key element does not match the schema"

**Cause:** OAuth table not created yet, or wrong schema

**Solution:** Run Step 1 above to create `mcelveen-oauth-tokens` table

### Issue: HTTP 400 Token Refresh Failed

**Cause:** SCHWAB_REFRESH_TOKEN in environment is expired (>7 days old)

**Solution:** Run Step 2–3 above to get fresh token from Schwab

### Issue: Token stored but next execution still fails

**Cause:** Table created but TTL not enabled, or DynamoDB throttling

**Solution:**
1. Check table TTL is enabled (see Step 1)
2. Wait 5 seconds between executions if table is throttled

---

## Next Steps

After v3.0.32 token rotation is working:
- ✅ No more manual token rotation needed
- ✅ System will run indefinitely with automatic 7-day refresh cycles
- ✅ Ready for v3.0.33 (Forex 24/5 market integration)

---

## Reference

- [Schwab OAuth Token Refresh Guide](./TOKEN_REFRESH.md)
- [AWS DynamoDB Console](https://console.aws.amazon.com/dynamodb)
- [AWS Lambda Console](https://console.aws.amazon.com/lambda)
- [CloudWatch Logs](https://console.aws.amazon.com/logs)
