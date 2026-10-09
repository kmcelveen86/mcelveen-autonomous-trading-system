# Schwab OAuth Token Refresh Guide

## Overview

The McElveen Autonomous Trading System uses **Charles Schwab OAuth 2.0** to authenticate with trading accounts. The system automatically refreshes the access token on every Lambda execution, but the initial **refresh token** must be manually obtained and configured.

This guide covers:
1. Getting your initial refresh token from Schwab Developer Portal
2. Configuring it in AWS Lambda
3. How automatic refresh works
4. Troubleshooting common issues

---

## Part 1: Obtain Initial Refresh Token from Schwab

### Step 1: Register Your Application

1. Go to [Schwab Developer Portal](https://developer.schwab.com)
2. Sign in with your Schwab account
3. Navigate to **My Apps** → **Create New App**
4. Fill in the form:
   - **App Name:** `McElveen Autonomous Trading System`
   - **App Description:** `Autonomous AI trading system with Lambda deployment`
   - **App Type:** Choose **Individual** (for personal trading) or **Firm** (for advisory)
   - **Redirect URI:** `http://localhost:8080/callback` (for local OAuth flow)

5. **Save** and note your:
   - `CLIENT_ID`
   - `CLIENT_SECRET`

### Step 2: Authorize Your Account (OAuth 2.0 Flow)

The Schwab OAuth flow requires you to:
1. Redirect to Schwab's authorization endpoint
2. Login with your credentials
3. Grant permission to your app
4. Receive an authorization code
5. Exchange the code for refresh + access tokens

**Option A: Use Schwab's OAuth Playground** (Easiest)

1. Go to [Schwab OAuth Playground](https://developer.schwab.com/oauth)
2. Select **Account Access Delegation (AAD)** flow
3. Enter your `CLIENT_ID` and `CLIENT_SECRET`
4. Click **Authorize**
5. You'll be redirected to Schwab login
6. Login and **Accept** the permissions
7. You'll receive:
   - `authorization_code` (valid for 5 minutes)
   - `access_token`
   - `refresh_token` (long-lived, typically 7 years)

**Important:** Copy the `refresh_token` immediately and store it securely.

**Option B: Manual OAuth Flow** (If needed for custom setup)

```bash
# Step 1: Get authorization code
curl -X GET "https://api.schwabapi.com/v1/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:8080/callback&response_type=code"

# Step 2: User logs in at Schwab and authorizes
# Step 3: Receive authorization code in redirect

# Step 4: Exchange code for tokens
curl -X POST "https://api.schwabapi.com/v1/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=YOUR_AUTH_CODE&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET&redirect_uri=http://localhost:8080/callback"
```

Response will include:
```json
{
  "access_token": "eyJh...",
  "refresh_token": "ey...",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "PlaceTrades AccountAccess MoveMoney"
}
```

---

## Part 2: Configure Token in AWS Lambda

### Option A: AWS Console (Easiest)

1. Go to [AWS Lambda Console](https://console.aws.amazon.com/lambda)
2. Find your function: `mcelveen-trading-system`
3. Click **Configuration** → **Environment variables**
4. Find or create `SCHWAB_REFRESH_TOKEN`
5. Paste your refresh token value
6. Click **Save**

### Option B: AWS CLI

```bash
aws lambda update-function-configuration \
  --function-name mcelveen-trading-system \
  --region us-east-2 \
  --environment Variables={SCHWAB_REFRESH_TOKEN=YOUR_REFRESH_TOKEN}
```

### Option C: Local Development (.env file)

For testing locally before deploying:

```bash
# 1. Create .env file from template
cp .env.example .env

# 2. Edit .env and add your refresh token
SCHWAB_REFRESH_TOKEN=YOUR_REFRESH_TOKEN_HERE

# 3. Local code loads it with python-dotenv
```

---

## Part 3: How Automatic Refresh Works

Once configured, the lambda_function.py **automatically** refreshes your access token on every execution:

### Token Refresh Flow (Automatic)

```
Lambda Execution Starts
    ↓
Load SCHWAB_REFRESH_TOKEN from environment
    ↓
Use refresh token to get new access_token
    ↓
access_token is valid for ~30 minutes
    ↓
Use access_token for all Schwab API calls
    ↓
On next Lambda execution, repeat
```

### Code Implementation

```python
def refresh_schwab_access_token(refresh_token):
    """
    Exchange refresh token for new access token.
    Called automatically on each Lambda execution.
    """
    url = "https://api.schwabapi.com/v1/oauth/token"
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': SCHWAB_CLIENT_ID,
        'client_secret': SCHWAB_CLIENT_SECRET
    }
    
    response = requests.post(url, data=payload, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        return data['access_token']  # New token valid for ~30 min
    else:
        raise Exception(f"Token refresh failed: HTTP {response.status_code}")
```

**Key Point:** The `refresh_token` itself **never expires** (typically valid 7 years), so you only need to obtain it once. The `access_token` (short-lived, ~30 min) is automatically refreshed on every Lambda run.

---

## Part 4: Monitoring & Troubleshooting

### Common Issues

#### Issue: "Token refresh failed: HTTP 400"

**Cause:** Refresh token is invalid, expired, or revoked

**Symptoms:**
- Lambda CloudWatch logs show: `[ERROR] Token refresh failed: HTTP 400`
- Trading does not execute
- System logs show initialization succeeds but first API call fails

**Solution:**
1. Regenerate a new refresh token from Schwab Developer Portal (follow Part 1 again)
2. Update Lambda environment variable with new token
3. Wait 2-5 minutes for Lambda to reload environment
4. Test with next scheduled execution

#### Issue: "Missing SCHWAB_REFRESH_TOKEN environment variable"

**Cause:** Token not set in Lambda environment

**Solution:**
1. Go to AWS Lambda → Configuration → Environment variables
2. Verify `SCHWAB_REFRESH_TOKEN` is present
3. If missing, add it (see Part 2)

#### Issue: "HTTP 401 Unauthorized" during trading

**Cause:** Access token failed to refresh (refresh token invalid)

**Solution:**
1. Check CloudWatch logs for HTTP 400 during refresh
2. If present, regenerate refresh token (see Part 4 "HTTP 400" above)
3. If logs show successful refresh but 401 later, it may be a scope issue (see below)

#### Issue: "HTTP 403 Forbidden" on specific endpoints

**Cause:** Your Schwab app lacks required OAuth scopes

**Required Scopes:**
- `PlaceTrades` — Place, modify, cancel orders
- `AccountAccess` — Read account details, positions, balances
- `MoveMoney` — Transfer funds (optional for trading)

**Solution:**
1. Go to Schwab Developer Portal
2. Check your app's **OAuth Scopes** setting
3. Ensure `PlaceTrades` and `AccountAccess` are enabled
4. Re-authorize to get new refresh token with correct scopes

---

## Part 5: Credential Rotation

### Recommended Rotation Schedule

| Credential | Rotation Frequency | Why |
|-----------|-------------------|-----|
| `SCHWAB_REFRESH_TOKEN` | On demand only | 7-year validity; no need to rotate unless you suspect compromise |
| `SCHWAB_CLIENT_SECRET` | Every 90 days | Schwab security policy for client secrets |
| `CLAUDE_API_KEY` | Every 6 months | Standard API key hygiene |

### How to Rotate Refresh Token

1. Go to Schwab Developer Portal
2. Revoke existing authorization (if option available)
3. Re-run OAuth flow (Part 1, Step 2)
4. Get new refresh token
5. Update Lambda environment variable
6. Test with next execution

### How to Rotate Client Secret

1. Go to Schwab Developer Portal → My Apps
2. Select your app
3. Find **Regenerate Secret** button
4. Copy new secret
5. Update `SCHWAB_CLIENT_SECRET` in Lambda
6. Test with next execution

---

## Part 6: Local Testing (Development)

### Test Token Refresh Locally

```python
# test_token_refresh.py
import os
from dotenv import load_dotenv
import requests

load_dotenv()

SCHWAB_CLIENT_ID = os.getenv('SCHWAB_CLIENT_ID')
SCHWAB_CLIENT_SECRET = os.getenv('SCHWAB_CLIENT_SECRET')
SCHWAB_REFRESH_TOKEN = os.getenv('SCHWAB_REFRESH_TOKEN')

def test_refresh():
    url = "https://api.schwabapi.com/v1/oauth/token"
    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': SCHWAB_REFRESH_TOKEN,
        'client_id': SCHWAB_CLIENT_ID,
        'client_secret': SCHWAB_CLIENT_SECRET
    }
    
    print("[TEST] Attempting token refresh...")
    response = requests.post(url, data=payload, timeout=10)
    
    if response.status_code == 200:
        data = response.json()
        print("[SUCCESS] Token refresh worked!")
        print(f"  Access Token: {data['access_token'][:50]}...")
        print(f"  Expires In: {data['expires_in']} seconds (~30 min)")
        return True
    else:
        print(f"[FAILED] HTTP {response.status_code}")
        print(f"  Error: {response.text}")
        return False

if __name__ == '__main__':
    test_refresh()
```

Run it:
```bash
python test_token_refresh.py
```

Expected output on success:
```
[TEST] Attempting token refresh...
[SUCCESS] Token refresh worked!
  Access Token: eyJhbGc...
  Expires In: 1800 seconds (~30 min)
```

---

## Part 7: Production Deployment Checklist

Before going live with Schwab API:

- [ ] Refresh token obtained from Schwab Developer Portal
- [ ] Token set in Lambda environment variables
- [ ] `SCHWAB_CLIENT_ID` and `SCHWAB_CLIENT_SECRET` configured
- [ ] OAuth scopes include `PlaceTrades` + `AccountAccess`
- [ ] Local test passes (test_token_refresh.py)
- [ ] Lambda execution succeeds without "Token refresh failed" errors
- [ ] First trade executes successfully (confirms token refresh + API access working)
- [ ] CloudWatch logs show successful OAuth flow
- [ ] Rotation schedule documented (90 days for client secret, on-demand for refresh token)

---

## References

- [Schwab Developer Portal](https://developer.schwab.com)
- [Schwab OAuth Documentation](https://developer.schwab.com/products/trader-api--individual)
- [Schwab API Reference](https://developer.schwab.com/docs/trader/apis)
- [OAuth 2.0 RFC 6749](https://tools.ietf.org/html/rfc6749)

---

## Support

If you encounter issues:

1. **Check CloudWatch Logs:**
   ```bash
   aws logs tail /aws/lambda/mcelveen-trading-system --follow
   ```

2. **Verify Environment Variables:**
   ```bash
   aws lambda get-function-configuration --function-name mcelveen-trading-system --query 'Environment.Variables'
   ```

3. **Contact:** kvmcelveen@outlook.com with:
   - CloudWatch error message
   - Timestamp of failure
   - Whether local test passed
   - Current Schwab app configuration (scopes, redirect URI)
