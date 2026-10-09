# Secrets Management & Environment Variables

## Overview

McElveen Autonomous Trading System **never hardcodes secrets**. All API keys, tokens, and credentials are loaded from environment variables at runtime.

---

## Local Development Setup

### 1. Create `.env` file (never commit!)

Copy from the template:
```bash
cp .env.example .env
```

### 2. Fill in your credentials

Edit `.env` with your actual values:
```
AWS_REGION=us-east-1
AWS_LAMBDA_FUNCTION_NAME=mcelveen-trading-system

SCHWAB_CLIENT_ID=your-actual-client-id
SCHWAB_CLIENT_SECRET=your-actual-secret
SCHWAB_REFRESH_TOKEN=your-refresh-token
SCHWAB_ACCOUNT_ID=your-account-id

CLAUDE_API_KEY=your-actual-api-key

PORTFOLIO_TARGET_ALLOCATION={"US_EQUITIES": 0.60, "INTERNATIONAL": 0.20, "BONDS": 0.15, "CASH": 0.05}
VIX_THRESHOLD_AGGRESSIVE=15
VIX_THRESHOLD_DEFENSIVE=25
DAILY_TRADE_FREQUENCY_CAP=5
```

### 3. Load in your Python code

For local development with `python-dotenv`:

```python
from dotenv import load_dotenv
import os

# Load .env file (only for local development, not in Lambda)
load_dotenv()

# Access credentials
client_id = os.getenv('SCHWAB_CLIENT_ID')
api_key = os.getenv('CLAUDE_API_KEY')
```

### 4. Verify `.env` is in `.gitignore`

```bash
grep "\.env" .gitignore  # Should show .env listed
```

---

## AWS Lambda Configuration

### Setting Environment Variables

**Option A: AWS Console**
1. Go to AWS Lambda → Your Function (`mcelveen-trading-system`)
2. Configuration → Environment variables
3. Add each key-value pair:
   - `SCHWAB_CLIENT_ID=xxx`
   - `SCHWAB_CLIENT_SECRET=xxx`
   - `SCHWAB_REFRESH_TOKEN=xxx`
   - `CLAUDE_API_KEY=xxx`
   - `AWS_REGION=us-east-1`

**Option B: AWS CLI**
```bash
aws lambda update-function-configuration \
  --function-name mcelveen-trading-system \
  --region us-east-1 \
  --environment Variables={SCHWAB_CLIENT_ID=xxx,SCHWAB_CLIENT_SECRET=xxx,...}
```

### Validation on Startup

The `lambda_function.py` validates all required environment variables when the handler loads:

```python
required_vars = {
    'SCHWAB_CLIENT_ID': SCHWAB_CLIENT_ID,
    'SCHWAB_CLIENT_SECRET': SCHWAB_CLIENT_SECRET,
    'SCHWAB_REFRESH_TOKEN': SCHWAB_REFRESH_TOKEN,
    'CLAUDE_API_KEY': CLAUDE_API_KEY,
}

missing_vars = [var for var, value in required_vars.items() if not value]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
```

**Result:** Lambda won't execute if any required credential is missing.

---

## Production / Paylinq Integration

For Paylinq production, use **AWS Secrets Manager** or **Parameter Store** instead of environment variables:

### AWS Secrets Manager (Recommended)

```python
import boto3
import json

secrets_client = boto3.client('secretsmanager', region_name='us-east-1')

def get_secrets():
    """Load secrets from AWS Secrets Manager"""
    try:
        response = secrets_client.get_secret_value(SecretId='mcelveen/trading/credentials')
        return json.loads(response['SecretString'])
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        raise

# In lambda_handler
secrets = get_secrets()
SCHWAB_CLIENT_ID = secrets['SCHWAB_CLIENT_ID']
CLAUDE_API_KEY = secrets['CLAUDE_API_KEY']
```

**Why Secrets Manager?**
- Secrets are encrypted at rest
- Automatic rotation support
- Audit trail of who accessed what
- No environment variables in Lambda console (can't be read by developers)

### AWS Parameter Store (Budget-friendly)

```python
ssm_client = boto3.client('ssm', region_name='us-east-1')

def get_parameter(name):
    """Load a parameter from Parameter Store"""
    response = ssm_client.get_parameter(Name=name, WithDecryption=True)
    return response['Parameter']['Value']

# Usage
client_id = get_parameter('/mcelveen/schwab/client_id')
api_key = get_parameter('/mcelveen/anthropic/api_key')
```

---

## Security Checklist

### Before Pushing to GitHub
- [ ] `.env` is in `.gitignore`
- [ ] No API keys visible in code
- [ ] No credentials in commit messages
- [ ] `config/trading_params.json` is in `.gitignore`

### Before Deploying to Lambda
- [ ] All required environment variables are set in Lambda console
- [ ] Lambda has IAM permission to read Secrets Manager (if using it)
- [ ] Credentials are rotated and valid
- [ ] CloudWatch logs are configured

### Before Paylinq Launch
- [ ] Switch to AWS Secrets Manager
- [ ] Enable MFA Delete on Secrets Manager
- [ ] Set up credential rotation policy (90 days)
- [ ] Audit trail is reviewed monthly
- [ ] Team access is restricted (principle of least privilege)

---

## Troubleshooting

### "Missing required environment variables" error

**Cause:** Lambda environment variables not set.

**Fix:**
```bash
aws lambda get-function-configuration \
  --function-name mcelveen-trading-system \
  --query 'Environment.Variables' \
  --region us-east-1
```

Verify all required vars are present. If missing, set them via console or CLI.

### Local development: "No module named dotenv"

**Cause:** `python-dotenv` not installed.

**Fix:**
```bash
pip install python-dotenv
```

### ".env file not found" warning (local)

**Cause:** You're running the code but `.env` doesn't exist.

**Fix:**
```bash
cp .env.example .env
# Then edit .env with your credentials
```

---

## Rotation Schedule

| Credential | Rotation | Why |
|------------|----------|-----|
| SCHWAB_CLIENT_SECRET | Every 90 days | Schwab security policy |
| CLAUDE_API_KEY | Every 6 months | Standard practice |
| SCHWAB_REFRESH_TOKEN | On demand only | Long-lived token, rotate if leaked |

---

## References

- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [OWASP: Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Anthropic API Security](https://docs.anthropic.com/claude/reference/api-overview)
- [Schwab OAuth Documentation](https://developer.schwab.com/products/trader-api--individual)

