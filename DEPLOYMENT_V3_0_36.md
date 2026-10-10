# McElveen Autonomous Forex Trading System
## v3.0.36 Deployment Guide
### Claude Sonnet 5 + Prompt Caching + 5-Minute Execution Cycles

---

## What's New in v3.0.36

✅ **Claude Sonnet 5 Integration**
- Replaces hardcoded macro analysis with AI-powered recommendations
- Analyzes interest rates, economic data, market sentiment
- Generates trading decisions: regime, conviction, pair recommendations

✅ **Prompt Caching**
- System prompt cached for 5 minutes
- Trading rules, pair definitions, guardrails cached
- ~90% savings on repeated tokens
- Estimated cost: **$2.80/month** (down from $45/month without caching)

✅ **5-Minute Execution Cycles**
- Continuous trading every 5 minutes during forex hours (Sun 5 PM - Fri 5 PM ET)
- ~1,440 executions/week
- Catches pip movements without excessive execution overhead

---

## Pre-Deployment Checklist

### 1. **Claude API Key**
Get your Claude API key from https://console.anthropic.com
- [x] Save it securely (you'll need this in Step 3)

### 2. **Schwab Refresh Token**
Generate a fresh token (valid for 24 hours):
```bash
cd /home/claude/mcelveen-autonomous-trading-system
python3 McElveenTokenRefresh.py
```
Copy the output **SCHWAB_REFRESH_TOKEN** (valid for 24 hours only)

### 3. **AWS Lambda Deployment**

**Option A: AWS CLI (if available)**
```bash
# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name Lambda-EventBridge-Role --query 'Role.Arn' --output text)

# Package code
zip -j mcelveen-v3.0.36.zip mcelveen_autonomous_forex_v3.0.36.py

# Create or update function
aws lambda update-function-code \
  --function-name mcelveen-autonomous-forex \
  --zip-file fileb://mcelveen-v3.0.36.zip \
  --region us-east-2
```

**Option B: AWS Console (manual)**
1. Go to **Lambda** → **Functions** → **mcelveen-autonomous-forex**
2. Click **Upload from** → **ZIP file**
3. Select `mcelveen-v3.0.36.zip` (zipped `mcelveen_autonomous_forex_v3.0.36.py`)
4. Click **Save**

### 4. **Update Environment Variables**

Go to **Lambda** → **mcelveen-autonomous-forex** → **Configuration** → **Environment variables**

Add/Update these:
```
SCHWAB_ACCOUNT_ID        | 7720-9306
SCHWAB_REFRESH_TOKEN     | <paste from McElveenTokenRefresh.py output>
SCHWAB_ACCESS_TOKEN      | (leave empty - refreshed automatically)
CLAUDE_API_KEY           | sk-ant-... (from https://console.anthropic.com)
CLAUDE_MODEL             | claude-sonnet-5
ENABLE_CACHE             | true
FOREX_TRADES_TABLE       | mcelveen-forex-trades
FOREX_METRICS_TABLE      | mcelveen-forex-metrics
```

**Save changes**

### 5. **Update EventBridge Rule** (Change from 15 min → 5 min)

**Option A: AWS CLI**
```bash
aws events put-rule \
  --name mcelveen-forex-trading-5min \
  --schedule-expression "rate(5 minutes)" \
  --state ENABLED \
  --region us-east-2

# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function \
  --function-name mcelveen-autonomous-forex \
  --region us-east-2 \
  --query 'Configuration.FunctionArn' \
  --output text)

# Get role ARN
ROLE_ARN=$(aws iam get-role \
  --role-name Lambda-EventBridge-Role \
  --query 'Role.Arn' \
  --output text)

# Update targets
aws events put-targets \
  --rule mcelveen-forex-trading-5min \
  --targets "Id"="1","Arn"="$LAMBDA_ARN","RoleArn"="$ROLE_ARN" \
  --region us-east-2
```

**Option B: AWS Console (manual)**
1. Go to **EventBridge** → **Rules**
2. Edit existing rule or create new rule **mcelveen-forex-trading-5min**
3. Set schedule: `rate(5 minutes)`
4. Set target: **Lambda function** → **mcelveen-autonomous-forex**
5. **Enable** the rule

### 6. **Test the Deployment**

**Option A: AWS CLI**
```bash
aws lambda invoke \
  --function-name mcelveen-autonomous-forex \
  --region us-east-2 \
  /tmp/test-output.json && cat /tmp/test-output.json | jq .
```

**Option B: Lambda Console**
1. Go to **Lambda** → **mcelveen-autonomous-forex**
2. Click **Test**
3. Create new test event (empty `{}`)
4. Click **Invoke**
5. Check **Response** tab for output

**Expected response:**
```json
{
  "statusCode": 200,
  "timestamp": "2026-10-10T04:15:00.000Z",
  "trading_mode": "FOREX_TRADING",
  "et_time": "00:15",
  "macro_analysis": {
    "regime": "USD_STRENGTH",
    "conviction": 0.75,
    "recommended_pairs": ["EUR/USD", "GBP/USD"],
    "pair_analysis": { ... }
  },
  "execution_results": [ ... ],
  "trades_executed": 2,
  "daily_metrics": { ... },
  "body": {
    "status": "SUCCESS",
    "message": "Executed 2 trades"
  }
}
```

---

## Cost Analysis (Weekly)

| Component | Cost | Notes |
|-----------|------|-------|
| Claude API (Sonnet 5) | $0.65 | With prompt caching (90% savings) |
| Schwab Commission | $0.00 | No forex commission |
| AWS Lambda | ~$0.10 | 1,440 invocations @ 500ms avg |
| DynamoDB | ~$0.05 | Pay-per-request, ~400 writes/week |
| CloudWatch | ~$0.02 | Logs + metrics |
| **TOTAL** | **$0.82/week** | **~$3.50/month** |

---

## Troubleshooting

### Error: "CLAUDE_API_KEY not set"
- Check Lambda environment variables
- Verify key format: `sk-ant-...` (starts with `sk-ant-`)
- Regenerate from https://console.anthropic.com

### Error: "SCHWAB_REFRESH_TOKEN expired"
- Generate fresh token: `python3 McElveenTokenRefresh.py`
- Update Lambda environment variable
- Token expires after 24 hours

### No trades executing
- Check CloudWatch logs: **Lambda** → **Monitor** → **View logs**
- Verify forex hours: Sun 5 PM - Fri 5 PM ET
- Check current ET time (run `date` in UTC and convert)
- Verify Schwab API connectivity

### High latency (>5 seconds)
- Check Schwab API response times
- Verify Claude API is responding (test in console.anthropic.com)
- May need to increase Lambda timeout (currently 60s)

---

## Monitoring

### CloudWatch Dashboard (Recommended)
Create a dashboard with:
- Daily PnL (CloudWatch Metric: `McElveen/Forex/DailyPnL`)
- Win Rate (CloudWatch Metric: `McElveen/Forex/WinRate`)
- Trades Completed (CloudWatch Metric: `McElveen/Forex/TradesCompleted`)
- Lambda Duration (built-in metric)

### DynamoDB Queries
```bash
# View today's trades
aws dynamodb query \
  --table-name mcelveen-forex-trades \
  --key-condition-expression "Date = :date" \
  --expression-attribute-values '{":date": {"S": "2026-10-10"}}' \
  --region us-east-2
```

---

## Next Steps

1. **Monitor first 24 hours** - Check logs, verify trades executing
2. **Tune macro parameters** - Adjust conviction thresholds if needed
3. **Add technical indicators** - Enhance Claude system prompt with RSI, MACD, etc.
4. **Scale to production** - Increase leverage, add more pairs, enable automated stop-losses

---

## Support

- **Issues**: Check CloudWatch Logs (/aws/lambda/mcelveen-autonomous-forex)
- **Questions**: Review code comments in mcelveen_autonomous_forex_v3.0.36.py
- **Schwab API**: https://developer.schwab.com/

---

**Deployment Status:** ✅ READY TO DEPLOY

**Last Updated:** 2026-10-10
**Version:** 3.0.36
