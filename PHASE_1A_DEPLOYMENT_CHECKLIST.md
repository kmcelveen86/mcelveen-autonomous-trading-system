# McElveen v3.0.33 - Phase 1A Deployment Checklist
## Forex 24/5 Infrastructure & Routing Setup

**Timeline:** Oct 9-15, 2026  
**Status:** Infrastructure configuration  
**Objective:** Deploy hybrid routing, validate time-based mode switching, establish forex data infrastructure

---

## Step 1: DynamoDB Tables Setup

### Table 1: mcelveen-forex-trades
**Purpose:** Log all forex trades (entry, exit, pips, P&L)

```
Table Name: mcelveen-forex-trades
Partition Key: Date (String) - YYYY-MM-DD
Sort Key: Timestamp (String) - ISO-8601 UTC
Region: us-east-2
Billing: PAY_PER_REQUEST

Attributes:
- Date (PK) - String
- Timestamp (SK) - String
- Pair - String (EUR/USD, GBP/USD, etc.)
- Direction - String (BUY/SELL)
- Quantity - Number
- EntryPrice - Number
- ExitPrice - Number (nullable)
- PipsGained - Number (nullable)
- PnL - Number
- Status - String (OPEN/CLOSED)
```

**AWS CLI:**
```bash
aws dynamodb create-table \
  --table-name mcelveen-forex-trades \
  --attribute-definitions AttributeName=Date,AttributeType=S AttributeName=Timestamp,AttributeType=S \
  --key-schema AttributeName=Date,KeyType=HASH AttributeName=Timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-2
```

### Table 2: mcelveen-forex-metrics
**Purpose:** Daily forex metrics (pnl, win-rate, trade counts)

```
Table Name: mcelveen-forex-metrics
Partition Key: Date (String) - YYYY-MM-DD
Sort Key: MetricType (String) - DAILY_SUMMARY, HOURLY, etc.
Region: us-east-2
Billing: PAY_PER_REQUEST

Attributes:
- Date (PK) - String
- MetricType (SK) - String
- DailyPnL - Number
- WinRate - Number (0-100)
- TradesCompleted - Number
- TradesOpen - Number
- AveragePips - Number
- Timestamp - String (ISO-8601)
```

**AWS CLI:**
```bash
aws dynamodb create-table \
  --table-name mcelveen-forex-metrics \
  --attribute-definitions AttributeName=Date,AttributeType=S AttributeName=MetricType,AttributeType=S \
  --key-schema AttributeName=Date,KeyType=HASH AttributeName=MetricType,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-2
```

---

## Step 2: Lambda Function Deployment

### Function: mcelveen-hybrid-trading-v3.0.33

**Configuration:**
```
Function Name: mcelveen-hybrid-trading-v3.0.33
Runtime: Python 3.11
Handler: index.lambda_handler
Timeout: 60 seconds
Memory: 512 MB
Region: us-east-2

Environment Variables:
- SCHWAB_ACCOUNT_ID = 7720-9306
- SCHWAB_ACCESS_TOKEN = (from token refresh)
- SCHWAB_REFRESH_TOKEN = (fresh token)
- FOREX_TRADES_TABLE = mcelveen-forex-trades
- FOREX_METRICS_TABLE = mcelveen-forex-metrics

IAM Permissions:
- dynamodb:PutItem (mcelveen-forex-trades)
- dynamodb:PutItem (mcelveen-forex-metrics)
- dynamodb:GetItem (mcelveen-forex-trades)
- dynamodb:GetItem (mcelveen-forex-metrics)
- cloudwatch:PutMetricData (McElveen/Forex namespace)
```

**Deployment:**
1. Go to AWS Lambda Console
2. Click **Create function**
3. Name: `mcelveen-hybrid-trading-v3.0.33`
4. Runtime: Python 3.11
5. Copy code from `v3.0.33_hybrid_forex_system.py`
6. Set environment variables (see above)
7. Deploy

---

## Step 3: EventBridge Rules Setup

### Rule 1: mcelveen-forex-trading-15min
**Purpose:** Trigger v3.0.33 every 15 minutes during forex trading hours

**Cron Schedule:**
```
Rule Name: mcelveen-forex-trading-15min
Schedule: Rate(15 minutes)
Timezone: America/New_York

EventBridge Pattern (for market-hours filtering):
{
  "source": ["aws.events"],
  "detail-type": ["Scheduled Event"]
}

Target: Lambda function mcelveen-hybrid-trading-v3.0.33
```

**AWS CLI:**
```bash
aws events put-rule \
  --name mcelveen-forex-trading-15min \
  --schedule-expression "rate(15 minutes)" \
  --state ENABLED \
  --region us-east-2

aws events put-targets \
  --rule mcelveen-forex-trading-15min \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-2:650589744593:function:mcelveen-hybrid-trading-v3.0.33","RoleArn"="arn:aws:iam::650589744593:role/service-role/Lambda-EventBridge-Role" \
  --region us-east-2
```

### Rule 2: mcelveen-forex-report-4pm
**Purpose:** Daily forex P&L report at 4:01 PM ET (end of equity trading)

**Cron Schedule:**
```
Rule Name: mcelveen-forex-report-4pm
Schedule: cron(1 16 ? * MON-FRI *) [UTC = 4:01 PM ET]
Timezone: UTC

Target: Lambda function mcelveen-forex-report-v1.0.0 (create next)
```

**AWS CLI:**
```bash
aws events put-rule \
  --name mcelveen-forex-report-4pm \
  --schedule-expression "cron(1 16 ? * MON-FRI *)" \
  --state ENABLED \
  --region us-east-2
```

---

## Step 4: Lambda IAM Role Setup

**Create Role: Lambda-EventBridge-Role**

Trust Policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com",
        "Service": "events.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Permissions Policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-2:650589744593:table/mcelveen-forex-trades",
        "arn:aws:dynamodb:us-east-2:650589744593:table/mcelveen-forex-metrics"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:us-east-2:650589744593:*"
    }
  ]
}
```

---

## Step 5: Validation Testing

### Test 1: Time-Based Routing
```bash
# Test during equity hours (9:30 AM-4 PM ET)
# Expected: [MODE] EQUITY

# Test during forex hours (5 PM-5 PM ET)
# Expected: [MODE] FOREX

# Test during market close (Fri 4 PM-Sun 5 PM ET)
# Expected: [MODE] CLOSED
```

### Test 2: Manual Lambda Invocation
```bash
aws lambda invoke \
  --function-name mcelveen-hybrid-trading-v3.0.33 \
  --region us-east-2 \
  /tmp/response.json

cat /tmp/response.json | jq .
```

Expected output:
```json
{
  "statusCode": 200,
  "body": {
    "mode": "FOREX|EQUITY|CLOSED",
    "status": "ROUTING_CONFIGURED",
    "macro_analysis": { ... }
  }
}
```

### Test 3: CloudWatch Logs
```bash
aws logs tail /aws/lambda/mcelveen-hybrid-trading-v3.0.33 --follow
```

Expected logs:
```
[TIME] 2026-10-09T23:30:00
[MODE] FOREX
[ROUTING] → FOREX TRADING (24/5 markets)
[STATUS] Phase 1A: Routing validated
```

---

## Step 6: Database Verification

### Verify DynamoDB Tables Created
```bash
aws dynamodb list-tables --region us-east-2

# Should show:
# - mcelveen-forex-trades
# - mcelveen-forex-metrics
```

### Add Sample Data (Testing)
```bash
aws dynamodb put-item \
  --table-name mcelveen-forex-trades \
  --item '{"Date":{"S":"2026-10-09"},"Timestamp":{"S":"2026-10-09T23:30:00Z"},"Pair":{"S":"EUR/USD"},"Direction":{"S":"BUY"},"Quantity":{"N":"1.0"},"EntryPrice":{"N":"1.0950"},"PnL":{"N":"10.00"},"Status":{"S":"OPEN"}}' \
  --region us-east-2
```

---

## Step 7: Environment Variable Verification

**In Lambda console, verify:**
- ✅ SCHWAB_ACCOUNT_ID = 7720-9306
- ✅ SCHWAB_REFRESH_TOKEN = (fresh token from generator)
- ✅ FOREX_TRADES_TABLE = mcelveen-forex-trades
- ✅ FOREX_METRICS_TABLE = mcelveen-forex-metrics

**Check Schwab credentials:**
```bash
# In Lambda code, test token refresh
# Expected: [OAUTH] ✅ Token refreshed (expires in 1800s)
```

---

## Completion Checklist

- [ ] DynamoDB table `mcelveen-forex-trades` created
- [ ] DynamoDB table `mcelveen-forex-metrics` created
- [ ] Lambda function `mcelveen-hybrid-trading-v3.0.33` deployed
- [ ] EventBridge rule `mcelveen-forex-trading-15min` created
- [ ] EventBridge rule `mcelveen-forex-report-4pm` created
- [ ] IAM role `Lambda-EventBridge-Role` configured
- [ ] Manual test passed (equity/forex routing works)
- [ ] CloudWatch logs show correct mode detection
- [ ] Fresh Schwab token verified in Lambda env vars
- [ ] Sample DynamoDB record written and verified

---

## Troubleshooting Phase 1A

### Issue: "Requested resource not found" (DynamoDB)
**Solution:** Verify table name in Lambda env vars matches created table names

### Issue: EventBridge not triggering Lambda
**Solution:** Verify IAM role has `lambda:InvokeFunction` permission for v3.0.33

### Issue: [MODE] shows EQUITY when it should be FOREX
**Solution:** Check local machine timezone; v3.0.33 uses US/Eastern (ET)

### Issue: "ResourceNotFoundException" on CloudWatch metrics
**Solution:** Verify Lambda IAM role has `cloudwatch:PutMetricData` permission

---

## Next Phase (1B)

Once Phase 1A validated:
1. Integrate CIO macro analysis into forex decision-making
2. Implement Schwab API forex order execution
3. Add guardrail validation (G1-G4)
4. Create forex report module (daily P&L)
5. Create diagnostic/debug Lambda

**Target:** Oct 15-Nov 5, 2026
