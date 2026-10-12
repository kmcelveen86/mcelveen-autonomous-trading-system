# McElveen Autonomous Forex Trading System - Lambda Deployment Guide

## ✅ Issue Fixed
The pydantic import error (`cannot import name 'ArgsKwargs' from 'pydantic_core._pydantic_core'`) was caused by outdated package versions:

**Root Cause:** `requirements.txt` specified:
- anthropic==0.7.0 (mid-2023, incompatible pydantic)
- boto3==1.28.85 (late 2023, version conflict)

**Solution:** Updated to current stable versions:
```
boto3>=1.35.0
anthropic>=0.25.0
requests>=2.31.0
python-dateutil>=2.8.2
pytz>=2023.3
python-dotenv>=1.0.0
pydantic>=2.5.0
```

**Deployment Package:** `mcelveen-forex-lambda-v3.0.36.zip` (29 MB)

---

## AWS Lambda Deployment Steps

### Step 1: Prepare Lambda Function
1. Go to AWS Lambda Console
2. Create new function: `mcelveen-autonomous-forex`
3. Runtime: Python 3.11
4. Memory: 512 MB (minimum)
5. Timeout: 60 seconds

### Step 2: Deploy Code
```bash
# Upload the deployment package
aws lambda update-function-code \
  --function-name mcelveen-autonomous-forex \
  --zip-file fileb://mcelveen-forex-lambda-v3.0.36.zip
```

### Step 3: Configure Environment Variables
```bash
aws lambda update-function-configuration \
  --function-name mcelveen-autonomous-forex \
  --environment Variables='{
    "SCHWAB_ACCOUNT_ID":"7720-9306",
    "SCHWAB_ACCESS_TOKEN":"<your_token>",
    "SCHWAB_REFRESH_TOKEN":"<your_refresh_token>",
    "FOREX_TRADES_TABLE":"mcelveen-forex-trades",
    "FOREX_METRICS_TABLE":"mcelveen-forex-metrics",
    "CLAUDE_API_KEY":"<your_api_key>",
    "CLAUDE_MODEL":"claude-sonnet-5",
    "ENABLE_CACHE":"true"
  }'
```

### Step 4: Create DynamoDB Tables
```bash
# Forex Trades Table
aws dynamodb create-table \
  --table-name mcelveen-forex-trades \
  --attribute-definitions \
    AttributeName=trade_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=S \
  --key-schema \
    AttributeName=trade_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-2

# Forex Metrics Table
aws dynamodb create-table \
  --table-name mcelveen-forex-metrics \
  --attribute-definitions \
    AttributeName=metric_date,AttributeType=S \
    AttributeName=timestamp,AttributeType=S \
  --key-schema \
    AttributeName=metric_date,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-2
```

### Step 5: Set Up EventBridge Trigger
```bash
# Create rule for 5-minute interval
aws events put-rule \
  --name mcelveen-forex-trigger \
  --schedule-expression "rate(5 minutes)" \
  --state ENABLED

# Add Lambda target
aws events put-targets \
  --rule mcelveen-forex-trigger \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-2:<ACCOUNT_ID>:function:mcelveen-autonomous-forex"

# Grant Lambda permission
aws lambda add-permission \
  --function-name mcelveen-autonomous-forex \
  --statement-id AllowEventBridgeInvoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-2:<ACCOUNT_ID>:rule/mcelveen-forex-trigger
```

### Step 6: Verify Deployment
```bash
# Check function state
aws lambda get-function --function-name mcelveen-autonomous-forex

# Check recent invocations
aws logs tail /aws/lambda/mcelveen-autonomous-forex --follow
```

---

## Trading Hours
- **Forex Active:** Sun 5:00 PM ET - Fri 5:00 PM ET
- **Idle Hours:** Saturday + Friday 5:00 PM - Sunday 5:00 PM (returns early, no cost)
- **EventBridge:** Runs every 5 minutes, Lambda validates internally

---

## System Architecture

### Components
1. **Router/Macro Analysis (Phase 1A)**
   - Detects current trading mode (EQUITY vs FOREX)
   - Runs Claude Sonnet 5 macro analysis
   - Uses prompt caching (~90% token savings)

2. **Execution (Phase 1B)**
   - Validates trading guardrails
   - Places orders via Schwab API
   - Journalizes trades to DynamoDB

3. **Monitoring**
   - CloudWatch logs (detailed execution)
   - DynamoDB metrics (P&L, win/loss rate)
   - Token usage tracking

### Forex Pairs Supported
- EUR/USD
- GBP/USD
- USD/JPY
- USD/CAD
- AUD/USD
- USD/CHF
- NZD/USD

---

## Cost Estimation
- **Anthropic API:** ~$2.80/month (with prompt caching)
- **DynamoDB:** ~$1/month (on-demand)
- **CloudWatch:** ~$0.50/month
- **EventBridge:** Free tier
- **Lambda:** ~$10/month (36,000 invocations/month)

**Total:** ~$14/month

---

## Troubleshooting

### Issue: pydantic import error
✅ **Fixed in v3.0.36** - Updated requirements.txt with compatible versions

### Issue: Schwab API 401/403
- Verify `SCHWAB_ACCESS_TOKEN` is current (refreshes via Lambda)
- Check `SCHWAB_REFRESH_TOKEN` is valid
- Ensure account ID matches `7720-9306`

### Issue: Lambda timeout
- Increase timeout to 60+ seconds
- Check network connectivity to Schwab API
- Verify CloudWatch logs for failure details

### Issue: Orders not executing
- Check guardrails aren't blocking (review `FAILED` status in logs)
- Verify account has available cash
- Check market hours validation logic

---

## Next Steps
1. ✅ Deploy mcelveen-forex-lambda-v3.0.36.zip
2. Set environment variables for Schwab & Claude API keys
3. Create DynamoDB tables
4. Enable EventBridge trigger
5. Monitor first 24 hours of trading in CloudWatch
6. Verify trade journaling in DynamoDB
