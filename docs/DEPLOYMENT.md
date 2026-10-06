# Deployment Guide — McElveen Autonomous Trading System

## Prerequisites

- AWS Account with appropriate IAM permissions
- AWS CLI configured (`aws configure`)
- Python 3.11+ installed locally
- Charles Schwab brokerage account (OAuth credentials)
- Anthropic API key (Claude API access)
- GitHub CLI (`gh`) for repository management

---

## Step 1: AWS Infrastructure Setup

### 1A. Create IAM Role for Lambda

Create `lambda-execution-role-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:Query"
      ],
      "Resource": "arn:aws:dynamodb:us-east-2:*:table/mcelveen-trading-ledger"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*"
    }
  ]
}
```

Create the role:
```bash
aws iam create-role \
  --role-name mcelveen-trading-lambda-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Service": "lambda.amazonaws.com"
        },
        "Action": "sts:AssumeRole"
      }
    ]
  }'

aws iam put-role-policy \
  --role-name mcelveen-trading-lambda-role \
  --policy-name mcelveen-policy \
  --policy-document file://lambda-execution-role-policy.json
```

### 1B. Create DynamoDB Table

```bash
aws dynamodb create-table \
  --table-name mcelveen-trading-ledger \
  --attribute-definitions AttributeName=execution_id,AttributeType=S \
  --key-schema AttributeName=execution_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --ttl-specification AttributeName=ttl,Enabled=true \
  --region us-east-2
```

Verify table creation:
```bash
aws dynamodb describe-table --table-name mcelveen-trading-ledger --region us-east-2
```

### 1C. Create CloudWatch Log Group

```bash
aws logs create-log-group \
  --log-group-name /aws/lambda/mcelveen-trading-system \
  --region us-east-2
```

---

## Step 2: Build & Package Lambda Function

### 2A. Prepare Local Environment

```bash
# Clone repository
git clone https://github.com/kmcelveen/mcelveen-autonomous-trading-system.git
cd mcelveen-autonomous-trading-system

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2B. Create Deployment Package

```bash
# Create deployment directory
mkdir lambda-deployment
cd lambda-deployment

# Copy all code files
cp ../lambda_function.py .
cp ../config/settings.py config/
cp ../core/*.py core/
cp ../requirements.txt .

# Install dependencies into package
pip install -r requirements.txt -t .

# Create ZIP file
zip -r ../mcelveen-trading-system.zip .

# Verify contents
unzip -l ../mcelveen-trading-system.zip | head -20
```

### 2C. Upload to AWS S3 (Optional, for CI/CD)

```bash
# Create S3 bucket for Lambda code
aws s3 mb s3://mcelveen-trading-lambda-code --region us-east-2

# Upload package
aws s3 cp mcelveen-trading-system.zip s3://mcelveen-trading-lambda-code/
```

---

## Step 3: Create Lambda Function

### 3A. Create Function from Local ZIP

```bash
aws lambda create-function \
  --function-name mcelveen-trading-system \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT_ID:role/mcelveen-trading-lambda-role \
  --handler lambda_function.handler \
  --zip-file fileb://mcelveen-trading-system.zip \
  --timeout 60 \
  --memory-size 512 \
  --environment Variables='{
    "AWS_REGION=us-east-2",
    "DYNAMODB_TABLE=mcelveen-trading-ledger",
    "CLOUDWATCH_NAMESPACE=McElveenTrading",
    "CONCENTRATION_LIMIT=0.15",
    "DAILY_TRADE_FREQUENCY_CAP=3",
    "VIX_THRESHOLD_AGGRESSIVE=15",
    "VIX_THRESHOLD_DEFENSIVE=25",
    "PORTFOLIO_TARGET_ALLOCATION={\"US_EQUITIES\": 0.60, \"INTERNATIONAL\": 0.20, \"BONDS\": 0.15, \"CASH\": 0.05}"
  }' \
  --region us-east-2
```

**Replace `ACCOUNT_ID` with your AWS account ID:**
```bash
# Get account ID
aws sts get-caller-identity --query Account --output text
```

### 3B. Add Secrets (OAuth & API Keys)

Do **NOT** add sensitive credentials to environment variables in the CLI. Instead:

**Option 1: AWS Secrets Manager (Recommended)**
```bash
# Store Schwab OAuth credentials
aws secretsmanager create-secret \
  --name mcelveen/schwab/oauth \
  --secret-string '{
    "client_id": "your-schwab-client-id",
    "client_secret": "your-schwab-client-secret"
  }' \
  --region us-east-2

# Store Anthropic API key
aws secretsmanager create-secret \
  --name mcelveen/anthropic/api-key \
  --secret-string "your-anthropic-api-key" \
  --region us-east-2
```

Update Lambda IAM policy to allow access:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue"
  ],
  "Resource": [
    "arn:aws:secretsmanager:us-east-2:*:secret:mcelveen/*"
  ]
}
```

**Option 2: AWS Lambda Secure String Environment Variables**
```bash
aws lambda update-function-configuration \
  --function-name mcelveen-trading-system \
  --environment Variables='{
    "SCHWAB_CLIENT_ID=your-id",
    "SCHWAB_CLIENT_SECRET=your-secret",
    "ANTHROPIC_API_KEY=your-key"
  }' \
  --region us-east-2
```

---

## Step 4: Create CloudWatch Trigger (Scheduled Execution)

### 4A. Create EventBridge Rule

```bash
# Create rule to execute every 6 hours (market open hours)
aws events put-rule \
  --name mcelveen-trading-trigger \
  --schedule-expression "cron(0 9,15,21,3 * * ? *)" \
  --state ENABLED \
  --description "Trigger McElveen Trading System every 6 hours" \
  --region us-east-2
```

**Schedule Explanation:**
- `9, 15, 21, 3` = 9am, 3pm, 9pm, 3am UTC
- Adjust for your market hours and timezone

### 4B. Add Lambda as Target

```bash
aws events put-targets \
  --rule mcelveen-trading-trigger \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-2:ACCOUNT_ID:function:mcelveen-trading-system" \
  --region us-east-2

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
  --function-name mcelveen-trading-system \
  --statement-id AllowEventBridgeInvoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:us-east-2:ACCOUNT_ID:rule/mcelveen-trading-trigger" \
  --region us-east-2
```

---

## Step 5: Manual Testing

### 5A. Test Lambda Locally

```bash
# Invoke Lambda function locally with test event
sam local invoke McElveenTradingFunction -e test-event.json

# Or use AWS Lambda Test Events
aws lambda invoke \
  --function-name mcelveen-trading-system \
  --payload '{}' \
  /tmp/lambda-response.json \
  --region us-east-2

# View response
cat /tmp/lambda-response.json
```

### 5B. Check CloudWatch Logs

```bash
# Get latest logs
aws logs tail /aws/lambda/mcelveen-trading-system --follow --region us-east-2

# Or view in console
aws logs describe-log-streams \
  --log-group-name /aws/lambda/mcelveen-trading-system \
  --region us-east-2
```

### 5C. Query DynamoDB Audit Trail

```bash
# Scan audit table for recent executions
aws dynamodb scan \
  --table-name mcelveen-trading-ledger \
  --limit 10 \
  --region us-east-2

# Get specific execution
aws dynamodb get-item \
  --table-name mcelveen-trading-ledger \
  --key '{"execution_id": {"S": "exec_20261006_143215_a7f2"}}' \
  --region us-east-2
```

---

## Step 6: Production Deployment Checklist

- [ ] **IAM Role Created** — Lambda has correct permissions
- [ ] **DynamoDB Table Created** — Audit trail storage ready
- [ ] **Secrets Stored** — OAuth & API keys in Secrets Manager
- [ ] **Lambda Function Deployed** — Code uploaded and configured
- [ ] **Environment Variables Set** — All config loaded correctly
- [ ] **EventBridge Rule Created** — Scheduled triggers configured
- [ ] **Lambda Permission Granted** — EventBridge can invoke function
- [ ] **Test Execution Passed** — Lambda runs without errors
- [ ] **CloudWatch Logs Verified** — All stages logged correctly
- [ ] **DynamoDB Records Verified** — Audit trail capturing executions
- [ ] **SNS Alerts Configured** — Email notifications on errors
- [ ] **Backup Policy Set** — DynamoDB backups enabled

---

## Step 7: Monitoring & Operations

### 7A. CloudWatch Dashboard

Create a dashboard to visualize system health:

```bash
aws cloudwatch put-dashboard \
  --dashboard-name McElveenTrading \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "metrics": [
            [ "McElveenTrading", "OrdersExecuted", { "stat": "Sum" } ],
            [ ".", "ExecutionTime", { "stat": "Average" } ],
            [ ".", "FailureRate", { "stat": "Average" } ]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-2",
          "title": "Trading System Metrics"
        }
      }
    ]
  }' \
  --region us-east-2
```

### 7B. Set CloudWatch Alarms

```bash
# Alert if daily trade frequency exceeds threshold
aws cloudwatch put-metric-alarm \
  --alarm-name mcelveen-daily-frequency-exceeded \
  --alarm-description "Alert if daily trade count > 3" \
  --metric-name DailyTradeFrequency \
  --namespace McElveenTrading \
  --statistic Maximum \
  --period 86400 \
  --threshold 3 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --region us-east-2

# Alert if error rate > 5%
aws cloudwatch put-metric-alarm \
  --alarm-name mcelveen-error-rate-spike \
  --alarm-description "Alert if error rate > 5%" \
  --metric-name ErrorRate \
  --namespace McElveenTrading \
  --statistic Average \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --region us-east-2
```

### 7C. SNS Notifications

```bash
# Create SNS topic for alerts
aws sns create-topic --name mcelveen-trading-alerts --region us-east-2

# Subscribe email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-2:ACCOUNT_ID:mcelveen-trading-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com \
  --region us-east-2
```

---

## Step 8: Updating Deployment

### 8A. Update Code

```bash
# Make changes locally
git checkout -b feature/update-guardrails
# ... edit files ...
git commit -am "Enhance guardrails validation"
git push origin feature/update-guardrails

# Create pull request (in GitHub)
# After review, merge to main
```

### 8B. Redeploy to Lambda

```bash
# Rebuild package (from repo root)
cd lambda-deployment
cp ../lambda_function.py .
# ... copy other modified files ...
zip -r ../mcelveen-trading-system.zip .

# Update Lambda function
aws lambda update-function-code \
  --function-name mcelveen-trading-system \
  --zip-file fileb://mcelveen-trading-system.zip \
  --region us-east-2

# Verify deployment
aws lambda get-function --function-name mcelveen-trading-system --region us-east-2
```

### 8C. Test After Update

```bash
# Invoke test
aws lambda invoke \
  --function-name mcelveen-trading-system \
  --payload '{}' \
  /tmp/lambda-response.json \
  --region us-east-2

# Check logs for errors
aws logs tail /aws/lambda/mcelveen-trading-system --follow --region us-east-2
```

---

## Step 9: Rollback Procedure

If deployment introduces errors:

```bash
# Get previous function version
aws lambda list-versions-by-function --function-name mcelveen-trading-system --region us-east-2

# Redeploy previous ZIP
aws lambda update-function-code \
  --function-name mcelveen-trading-system \
  --zip-file fileb://mcelveen-trading-system-v1.zip \
  --region us-east-2

# Verify rollback
aws logs tail /aws/lambda/mcelveen-trading-system --follow --region us-east-2
```

---

## Troubleshooting

### Lambda Timeout (60 seconds exceeded)
- Increase timeout: `aws lambda update-function-configuration --function-name mcelveen-trading-system --timeout 120`
- Check CloudWatch Logs for slow API calls
- Consider caching VIX/interest rates to reduce CIO analysis latency

### DynamoDB Throttling
- Switch from `PAY_PER_REQUEST` to provisioned capacity
- Set read capacity to 5, write capacity to 5 (adjustable based on usage)

### OAuth Token Refresh Failures
- Verify Schwab credentials in Secrets Manager
- Check Schwab API status page
- Implement exponential backoff retry logic in `_refresh_oauth_token()`

### Claude API Rate Limiting
- Check Anthropic account rate limits
- Implement backoff strategy in `select_assets()`
- Consider batch requests if multiple portfolios

---

## Cost Estimation (Monthly)

| Service | Estimated Cost | Notes |
|---|---|---|
| **Lambda** | $0.20 | ~1,000 invocations × 5s avg = 5,000 GB-s → $0.20 |
| **DynamoDB** | $1.25 | ~50 executions/day × 30 days = 1,500 writes → $1.25 |
| **CloudWatch** | $0.50 | Logs + metrics storage |
| **Secrets Manager** | $0.40 | 1 secret accessed daily |
| **API Calls** | $5–20 | Varies: Schwab free, Claude ~$0.01–0.05 per call |
| **Total** | ~$8–27 | Highly variable based on execution frequency |

---

## Production Best Practices

1. **Always use Secrets Manager** — Never hardcode API keys
2. **Enable Lambda versioning** — Easy rollbacks
3. **Set up SNS alerts** — Know when things break
4. **Monitor DynamoDB** — Watch for throttling
5. **Schedule regular audits** — Review execution logs monthly
6. **Backup DynamoDB** — Point-in-time recovery enabled
7. **Use VPC (optional)** — If connecting to on-premises systems
8. **Enable X-Ray tracing** — Debug end-to-end latency issues

---

**Document Version:** 1.0  
**Last Updated:** 2026-10-06  
**Maintained By:** Kevin McElveen
